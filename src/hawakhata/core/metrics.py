"""Zero-dependency, thread-safe Prometheus text-format metrics and per-turn stage telemetry.

Labels are bounded enums (route templates, status codes, outcome/provider names) — never user
text, prompts, IPs, coordinates or secrets.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from hawakhata.core.logging import get_logger

_log = get_logger(__name__)
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
LabelKey = tuple[tuple[str, str], ...]


def _fmt_labels(key: LabelKey, extra: tuple[tuple[str, str], ...] = ()) -> str:
    pairs = key + extra
    if not pairs:
        return ""
    esc = (v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") for _, v in pairs)
    return "{" + ",".join(f'{k}="{v}"' for (k, _), v in zip(pairs, esc, strict=True)) + "}"


class _Metric:
    kind = ""

    def __init__(self, name: str, help_text: str, labels: tuple[str, ...] = ()) -> None:
        self.name, self.help_text, self.labels = name, help_text, labels
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> LabelKey:
        if set(labels) != set(self.labels):
            raise ValueError(f"{self.name} expects labels {self.labels}")
        return tuple((k, str(labels[k])) for k in self.labels)

    def render(self) -> list[str]:
        return [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} {self.kind}"]


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str, labels: tuple[str, ...] = ()) -> None:
        super().__init__(name, help_text, labels)
        self._values: dict[LabelKey, float] = {} if labels else {(): 0.0}

    def inc(self, amount: float = 1.0, /, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(self._key(labels), 0.0)

    def render(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        return super().render() + [f"{self.name}{_fmt_labels(k)} {v:g}" for k, v in items]


class Histogram(_Metric):
    kind = "histogram"

    def __init__(self, name: str, help_text: str, labels: tuple[str, ...] = ()) -> None:
        super().__init__(name, help_text, labels)
        self._series: dict[LabelKey, tuple[list[int], float, int]] = {}

    def observe(self, value: float, /, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            counts, total, n = self._series.get(key, ([0] * len(_BUCKETS), 0.0, 0))
            for i, bound in enumerate(_BUCKETS):
                if value <= bound:
                    counts[i] += 1
            self._series[key] = (counts, total + value, n + 1)

    def render(self) -> list[str]:
        with self._lock:
            items = sorted((k, (list(c), s, n)) for k, (c, s, n) in self._series.items())
        lines = super().render()
        for key, (counts, total, n) in items:
            for bound, count in zip(_BUCKETS, counts, strict=True):
                lines.append(
                    f"{self.name}_bucket{_fmt_labels(key, (('le', f'{bound:g}'),))} {count}"
                )
            lines.append(f"{self.name}_bucket{_fmt_labels(key, (('le', '+Inf'),))} {n}")
            lines.append(f"{self.name}_sum{_fmt_labels(key)} {total:.6f}")
            lines.append(f"{self.name}_count{_fmt_labels(key)} {n}")
        return lines


HTTP_REQUESTS = Counter(
    "hawakhata_http_requests_total", "HTTP requests by route and status.", ("route", "status")
)
HTTP_DURATION = Histogram(
    "hawakhata_http_request_duration_seconds", "HTTP latency by route.", ("route", "status")
)
CHAT_OUTCOMES = Counter(
    "hawakhata_chat_outcomes_total", "Ask HawaKhata turn outcomes.", ("outcome",)
)
GUARDRAIL_BLOCKS = Counter(
    "hawakhata_guardrail_blocks_total", "Guardrail blocks by category.", ("category",)
)
UPSTREAM_ERRORS = Counter(
    "hawakhata_upstream_errors_total", "Failed upstream calls by provider.", ("provider",)
)
RATE_LIMIT_REJECTIONS = Counter(
    "hawakhata_rate_limit_rejections_total", "Requests rejected with HTTP 429."
)
_ALL: tuple[_Metric, ...] = (
    HTTP_REQUESTS,
    HTTP_DURATION,
    CHAT_OUTCOMES,
    GUARDRAIL_BLOCKS,
    UPSTREAM_ERRORS,
    RATE_LIMIT_REJECTIONS,
)


def render_prometheus() -> str:
    """Render every metric in Prometheus text exposition format 0.0.4."""
    return "\n".join(line for metric in _ALL for line in metric.render()) + "\n"


@dataclass
class TurnTelemetry:
    """Stage timings + outcome for one chat/brief turn, emitted as one structured log line."""

    kind: str
    outcome: str = "deterministic_route"
    stages: dict[str, float] = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Accumulate wall time spent in ``name`` (aq, gemini, grounding)."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (time.perf_counter() - t0) * 1000

    def finish[T](self, result: T) -> T:
        """Log the turn (and count chat outcomes), then return ``result`` unchanged."""
        if self.kind == "chat_turn":
            CHAT_OUTCOMES.inc(outcome=self.outcome)
        timings = {
            f"{s}_ms": round(self.stages.get(s, 0.0), 1) for s in ("aq", "gemini", "grounding")
        }
        total_ms = round((time.perf_counter() - self.started) * 1000, 1)
        _log.info(self.kind, extra={**timings, "total_ms": total_ms, "outcome": self.outcome})
        return result
