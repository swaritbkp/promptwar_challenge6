"""Zero-extra-dependency async load benchmark (httpx only).

Usage:
    python loadtests/bench.py --base-url http://127.0.0.1:18080 --concurrency 20 --duration 15

Mixed workload per worker, in a fixed weighted rotation: /healthz, /readyz, /api/v1/brief and
/api/v1/chat (a deterministic-route question, so no Gemini key is needed). Prints total
requests, RPS, status breakdown, error rate and p50/p95/p99 latency overall and per endpoint.

``--simulated-clients N`` spreads requests over N client IPs via ``X-Forwarded-For`` (what
Cloud Run's front end appends), so a benchmark against a container with TRUSTED_PROXY_HOPS=1
measures throughput instead of one client's 60/min rate limit. Default 0 = one client.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx

PROFILE: dict[str, Any] = {
    "id": "fam_bench",
    "name": "Household",
    "location": {"lat": 28.4595, "lng": 77.0266},
    "members": [{"id": "m1", "name": "Member", "age_band": "31_41"}],
}
# (name, method, path, json body, weight)
WORKLOAD: list[tuple[str, str, str, dict[str, Any] | None, int]] = [
    ("healthz", "GET", "/healthz", None, 1),
    ("readyz", "GET", "/readyz", None, 1),
    ("brief", "POST", "/api/v1/brief", {"profile": PROFILE}, 2),
    ("chat", "POST", "/api/v1/chat", {"message": "Is it safe to walk now?"}, 2),
]


@dataclass
class Results:
    latencies_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    statuses: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))


def percentile(sorted_ms: list[float], pct: float) -> float:
    """Nearest-rank percentile of an ascending list (0 when empty)."""
    if not sorted_ms:
        return 0.0
    rank = max(1, math.ceil(pct / 100 * len(sorted_ms)))
    return sorted_ms[rank - 1]


async def worker(
    idx: int, client: httpx.AsyncClient, deadline: float, clients: int, results: Results
) -> None:
    """Issue requests in weighted rotation until the deadline."""
    plan = [w for w in WORKLOAD for _ in range(w[4])]
    rotation = itertools.islice(itertools.cycle(plan), idx % len(plan), None)
    for seq, (name, method, path, body, _) in enumerate(rotation):
        if time.perf_counter() >= deadline:
            return
        headers = {}
        if clients > 0:
            n = (idx * 7919 + seq) % clients
            headers["X-Forwarded-For"] = f"10.{n // 65536 % 256}.{n // 256 % 256}.{n % 256}"
        started = time.perf_counter()
        try:
            resp = await client.request(method, path, json=body, headers=headers)
            status = str(resp.status_code)
        except httpx.HTTPError as exc:
            status = f"ERR:{type(exc).__name__}"
        results.latencies_ms[name].append((time.perf_counter() - started) * 1000)
        results.statuses[name][status] += 1


def report(results: Results, elapsed_s: float) -> None:
    """Print the summary tables."""
    all_ms = sorted(ms for series in results.latencies_ms.values() for ms in series)
    total = len(all_ms)
    overall: Counter[str] = Counter()
    for counts in results.statuses.values():
        overall.update(counts)
    errors = sum(n for s, n in overall.items() if not s.startswith("2"))
    server_errors = sum(n for s, n in overall.items() if s.startswith(("5", "ERR")))
    print(f"\nDuration        {elapsed_s:.2f} s")
    print(f"Total requests  {total}")
    print(f"RPS             {total / elapsed_s:.1f}")
    print("Status codes    " + ", ".join(f"{s}={n}" for s, n in sorted(overall.items())))
    print(f"Error rate      {100 * errors / max(1, total):.2f} % (non-2xx, incl. 429)")
    print(f"5xx/transport   {100 * server_errors / max(1, total):.2f} %")
    header = (
        f"\n{'endpoint':<10}{'reqs':>7}{'rps':>8}{'err%':>8}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}"
    )
    print(header)
    print("-" * (len(header) - 1))
    rows = [(name, sorted(results.latencies_ms[name])) for name, *_ in WORKLOAD]
    rows.append(("OVERALL", all_ms))
    for name, series in rows:
        counts = overall if name == "OVERALL" else results.statuses[name]
        bad = sum(n for s, n in counts.items() if not s.startswith("2"))
        print(
            f"{name:<10}{len(series):>7}{len(series) / elapsed_s:>8.1f}"
            f"{100 * bad / max(1, len(series)):>8.2f}"
            f"{percentile(series, 50):>9.1f}{percentile(series, 95):>9.1f}"
            f"{percentile(series, 99):>9.1f}"
        )


async def main() -> None:
    """Parse args, run workers for --duration seconds, print the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--simulated-clients", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    results = Results()
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(
        base_url=args.base_url, timeout=args.timeout, limits=limits
    ) as client:
        (await client.get("/healthz")).raise_for_status()  # fail fast if the target is down
        started = time.perf_counter()
        deadline = started + args.duration
        await asyncio.gather(
            *(
                worker(i, client, deadline, args.simulated_clients, results)
                for i in range(args.concurrency)
            )
        )
        elapsed = time.perf_counter() - started
    print(
        f"target={args.base_url} concurrency={args.concurrency} duration={args.duration}s "
        f"simulated_clients={args.simulated_clients or 1}"
    )
    report(results, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
