"""Bounded session store for multi-turn conversational agents."""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single turn in a conversation."""

    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChatSession:
    """In-memory multi-turn chat session with bounded turn count."""

    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    """Thread-safe bounded in-memory session cache with LRU eviction."""

    def __init__(
        self,
        max_entries: int = 1000,
        ttl_s: float = 3600.0,
        max_turns: int = 20,
        max_sessions: int | None = None,
        session_ttl_s: float | None = None,
    ) -> None:
        """Initialize session store with capacity and lifetime limits."""
        self.max_entries = max_sessions if max_sessions is not None else max_entries
        self.ttl_s = session_ttl_s if session_ttl_s is not None else ttl_s
        self.max_turns = max_turns
        self._sessions: collections.OrderedDict[str, ChatSession] = collections.OrderedDict()

    def _evict_expired(self, now: float) -> None:
        expired_keys = [
            k for k, s in self._sessions.items() if (now - s.last_active_at) > self.ttl_s
        ]
        for k in expired_keys:
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
        if sess is None:
            return []
        return [{"role": m.role, "content": m.content} for m in sess.messages]

    def list_active_sessions(self) -> list[str]:
        """List session IDs of all active non-expired sessions."""
        self._evict_expired(time.time())
        return list(self._sessions.keys())

    def get_or_create(
        self,
        session_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession:
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
            session_id=session_id,
            created_at=now,
            last_active_at=now,
            metadata=metadata or {},
        )
        self._sessions[session_id] = new_sess
        return new_sess

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> ChatSession:
        """Append a message turn to the session, trimming older turns if over max."""
        sess = self.get_or_create(session_id)
        sess.messages.append(ChatMessage(role=role, content=content))
        if len(sess.messages) > self.max_turns:
            excess = len(sess.messages) - self.max_turns
            sess.messages = sess.messages[excess:]
        sess.last_active_at = time.time()
        self._sessions.move_to_end(session_id)
        return sess

    def clear(self) -> None:
        """Clear all active sessions."""
        self._sessions.clear()
