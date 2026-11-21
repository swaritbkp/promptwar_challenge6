"""Bounded conversation memory: in-memory LRU, Redis (multi-instance) and a failover wrapper."""

from __future__ import annotations

import collections
import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from hawakhata.core.cache import REDIS_ERRORS, record_redis_error

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from hawakhata.config import Settings

HistoryEntry = dict[str, str]


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChatSession:
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionBackend(Protocol):
    """Async conversation-memory contract shared by every store the agent can use."""

    async def history(self, session_id: str) -> list[HistoryEntry]:
        """Return the stored turns, oldest first."""
        ...

    async def append_turns(self, session_id: str, turns: Sequence[tuple[str, str]]) -> None:
        """Append ``(role, content)`` turns, keeping only the newest ``max_turns``."""
        ...


def bounded_history(
    entries: Sequence[HistoryEntry], max_turns: int, max_chars: int
) -> list[HistoryEntry]:
    """Keep the newest ``max_turns`` entries, then drop oldest until rendered size <= max_chars."""
    kept = list(entries[-max_turns:]) if max_turns > 0 else []
    sizes = [len(e["role"]) + len(e["content"]) + 3 for e in kept]  # "role: content" + newline
    total = sum(sizes)
    while kept and total > max_chars:
        kept.pop(0)
        total -= sizes.pop(0)
    return kept


class SessionStore:
    """Bounded in-memory session cache with LRU eviction."""

    def __init__(
        self,
        max_entries: int = 1000,
        ttl_s: float = 3600.0,
        max_turns: int = 20,
        max_sessions: int | None = None,
        session_ttl_s: float | None = None,
    ) -> None:
        self.max_entries = max_sessions if max_sessions is not None else max_entries
        self.ttl_s = session_ttl_s if session_ttl_s is not None else ttl_s
        self.max_turns = max_turns
        self._sessions: collections.OrderedDict[str, ChatSession] = collections.OrderedDict()

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, s in self._sessions.items() if (now - s.last_active_at) > self.ttl_s]
        for k in expired:
            del self._sessions[k]

    def get(self, session_id: str) -> ChatSession | None:
        """Retrieve an existing session if not expired."""
        now = time.time()
        self._evict_expired(now)
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        sess.last_active_at = now
        self._sessions.move_to_end(session_id)
        return sess

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Retrieve message history for a session."""
        sess = self.get(session_id)
        return [{"role": m.role, "content": m.content} for m in sess.messages] if sess else []

    def list_active_sessions(self) -> list[str]:
        """List session IDs of all active non-expired sessions."""
        self._evict_expired(time.time())
        return list(self._sessions.keys())

    def get_or_create(self, session_id: str, metadata: dict[str, Any] | None = None) -> ChatSession:
        """Retrieve an existing active session or initialize a new one."""
        now = time.time()
        self._evict_expired(now)
        if session_id in self._sessions:
            sess = self._sessions[session_id]
            sess.last_active_at = now
            if metadata:
                sess.metadata.update(metadata)
            self._sessions.move_to_end(session_id)
            return sess
        while len(self._sessions) >= self.max_entries:
            self._sessions.popitem(last=False)
        new_sess = ChatSession(
            session_id=session_id, created_at=now, last_active_at=now, metadata=metadata or {}
        )
        self._sessions[session_id] = new_sess
        return new_sess

    def add_message(self, session_id: str, role: str, content: str) -> ChatSession:
        """Append a message turn to the session, trimming older turns if over max."""
        sess = self.get_or_create(session_id)
        sess.messages.append(ChatMessage(role=role, content=content))
        if len(sess.messages) > self.max_turns:
            sess.messages = sess.messages[len(sess.messages) - self.max_turns :]
        sess.last_active_at = time.time()
        self._sessions.move_to_end(session_id)
        return sess

    def clear(self) -> None:
        """Clear all active sessions."""
        self._sessions.clear()

    async def history(self, session_id: str) -> list[HistoryEntry]:
        """Async view of :meth:`get_history` (SessionBackend contract)."""
        return self.get_history(session_id)

    async def append_turns(self, session_id: str, turns: Sequence[tuple[str, str]]) -> None:
        """Async batch of :meth:`add_message` calls (SessionBackend contract)."""
        for role, content in turns:
            self.add_message(session_id, role, content)


def _decode_turns(raw: bytes | str | None) -> list[HistoryEntry]:
    """Parse a stored JSON turn list; anything malformed reads as an empty history."""
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [
        {"role": t["role"], "content": t["content"]}
        for t in data
        if isinstance(t, dict)
        and isinstance(t.get("role"), str)
        and isinstance(t.get("content"), str)
    ]


class RedisSessionStore:
    """Session turns as one JSON list per session in Redis, refreshed with ``SETEX`` (sliding TTL).

    Every Cloud Run instance sharing the Redis sees the same conversation for a ``session_id``.
    Keys are a SHA-256 of the session id, so client-supplied ids never become raw key names.
    """

    def __init__(self, client: Redis, ttl_s: int, max_turns: int, prefix: str = "hk:sess:") -> None:
        if ttl_s <= 0 or max_turns <= 0:
            raise ValueError("ttl_s and max_turns must be positive")
        self._client, self._ttl_s, self._max_turns, self._prefix = client, ttl_s, max_turns, prefix

    def _key(self, session_id: str) -> str:
        return self._prefix + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]

    async def history(self, session_id: str) -> list[HistoryEntry]:
        """Return stored turns and slide the TTL forward."""
        key = self._key(session_id)
        turns = _decode_turns(await self._client.get(key))
        if turns:
            await self._client.expire(key, self._ttl_s)
        return turns

    async def append_turns(self, session_id: str, turns: Sequence[tuple[str, str]]) -> None:
        """Append turns, trim to ``max_turns`` and rewrite with ``SETEX`` (TTL refresh)."""
        key = self._key(session_id)
        stored = _decode_turns(await self._client.get(key))
        stored += [{"role": role, "content": content} for role, content in turns]
        payload = json.dumps(stored[-self._max_turns :], ensure_ascii=False)
        await self._client.setex(key, self._ttl_s, payload)


class FailoverSessionStore:
    """Use the primary (Redis) store; on a transient Redis error degrade to in-memory, never 500."""

    def __init__(self, primary: SessionBackend, fallback: SessionStore) -> None:
        self.primary, self.fallback = primary, fallback

    async def history(self, session_id: str) -> list[HistoryEntry]:
        """Primary history, or this instance's in-memory history during an outage."""
        try:
            return await self.primary.history(session_id)
        except REDIS_ERRORS as exc:
            record_redis_error(exc, "session_get")
            return await self.fallback.history(session_id)

    async def append_turns(self, session_id: str, turns: Sequence[tuple[str, str]]) -> None:
        """Write to the primary, or to in-memory during an outage."""
        try:
            await self.primary.append_turns(session_id, turns)
        except REDIS_ERRORS as exc:
            record_redis_error(exc, "session_set")
            await self.fallback.append_turns(session_id, turns)


def build_session_store(settings: Settings, client: Redis | None) -> SessionBackend:
    """Redis-backed (with in-memory failover) when a client exists, else bounded in-memory."""
    memory = SessionStore(
        max_sessions=settings.session_max,
        session_ttl_s=settings.session_ttl_s,
        max_turns=settings.session_max_turns,
    )
    if client is None:
        return memory
    redis_store = RedisSessionStore(client, settings.session_ttl_s, settings.session_max_turns)
    return FailoverSessionStore(redis_store, memory)
