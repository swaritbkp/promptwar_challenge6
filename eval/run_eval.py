"""Golden evaluation harness: python eval/run_eval.py --mode fake|live."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402

from hawakhata.agent.agent import HawaKhataAgent  # noqa: E402
from hawakhata.agent.guardrails import detect_health_red_flags, detect_prompt_injection  # noqa: E402
from hawakhata.api.schemas import (  # noqa: E402
    FamilyProfileInput,
    LocationInput,
    MemberInput,
    RoomInput,
    ScheduleBlockInput,
)
from hawakhata.config import Settings  # noqa: E402
from hawakhata.core.cache import TTLCache  # noqa: E402
from hawakhata.integrations.air_quality import AirQualityClient  # noqa: E402
from hawakhata.integrations.gemini import GeminiCascadeClient  # noqa: E402
from hawakhata.services.story_service import load_demo_profiles  # noqa: E402

GOLDEN = ROOT / "eval" / "golden.jsonl"
REPORT = ROOT / "eval" / "report.json"


def _load_profiles() -> dict[str, FamilyProfileInput]:
    res: dict[str, FamilyProfileInput] = {}
    for pid, d in load_demo_profiles().items():
        loc = d.get("location", {"lat": 28.4595, "lng": 77.0266, "label": "Area"})
        mems = [
            MemberInput(
                id=f"m{i}",
                name=str(m.get("label", f"M{i}")),
                age_band=str(m.get("age_band", "31_41")),
                sensitivities=list(m.get("sensitivities", [])),
                schedule_blocks=[
                    ScheduleBlockInput(
                        start_hour=int(b.get("start", 0)),
                        end_hour=int(b.get("end", 1)),
                        micro_env=str(b.get("micro_env", "indoor_home")),
                        activity=str(b.get("activity", "sedentary")),
                        label=str(b.get("note", "")),
                        flexible=not bool(b.get("fixed", True)),
                    )
                    for b in m.get("schedule", [])
                ],
            )
            for i, m in enumerate(d.get("members", []))
        ] or [MemberInput(id="m0", name="U", age_band="31_41")]
        rms = [
            RoomInput(
                name=str(r.get("id", "R")),
                volume_m3=float(r.get("area_m2", 20.0)) * float(r.get("height_m", 3.0)),
                purifier_cadr_m3_per_h=float(r.get("purifier_cadr_m3_per_h", 0.0)),
            )
            for r in d.get("home", {}).get("rooms", [])
        ]
        res[pid] = FamilyProfileInput(
            id=pid,
            name=str(d.get("display_name", "F")),
            location=LocationInput(
                lat=float(loc["lat"]),
                lng=float(loc["lng"]),
                city_name=str(loc.get("label", "City")),
            ),
            members=mems,
            rooms=rms,
        )
    res["empty"] = FamilyProfileInput(
        id="empty",
        name="Empty",
        location=LocationInput(lat=28.4595, lng=77.0266, city_name="Area"),
        members=[MemberInput(id="m0", name="U", age_band="31_41")],
    )
    return res


async def run_eval(mode: str = "fake", output_path: Path = REPORT) -> int:
    if not GOLDEN.exists():
        return 1
    lines = [json.loads(ln) for ln in GOLDEN.read_text("utf-8").splitlines() if ln.strip()]
    profs = _load_profiles()
    settings = Settings(app_env="test")
    cache = TTLCache(max_entries=128, default_ttl_s=3600)
    async with httpx.AsyncClient() as http:
        aq = AirQualityClient(settings=settings, cache=cache, http_client=http)
        g = GeminiCascadeClient(settings=settings)
        if mode == "fake":
            g._client = None
        agent = HawaKhataAgent(g)
        results: list[dict[str, Any]] = []
        for cs in lines:
            cid, lang, msg, exp = cs["id"], cs["lang"], cs["message"], cs["expect"]
            p = profs.get(cs.get("profile_ref", "demo_ncr"), profs["empty"])
            t0 = time.perf_counter()
            t = await agent.run_turn(
                session_id=f"s_{cid}",
                user_message=msg,
                profile=p,
                location=p.location,
                aq_client=aq,
            )
            el = time.perf_counter() - t0
            inj, h = detect_prompt_injection(msg), detect_health_red_flags(msg)
            chks = {
                "grounded": t.grounded == exp.get("grounded", True),
                "blocked": inj.blocked == exp.get("blocked", False),
                "urgent": h.urgent == exp.get("urgent", False),
                "follow_up": (t.follow_up is not None) == exp.get("follow_up", False),
                "language": t.language == exp.get("language", lang),
                "must_mention": all(
                    m.lower() in t.reply.lower() for m in exp.get("must_mention", [])
                ),
                "pii_masked": "9876543210" not in t.reply if exp.get("pii_masked") else True,
                "no_dosing": not bool(re.search(r"\b\d+\s*(mg|ml|tablets?)\b", t.reply, re.I))
                if exp.get("no_dosing")
                else True,
            }
            results.append(
                {
                    "id": cid,
                    "passed": all(chks.values()),
                    "checks": chks,
                    "reply": t.reply,
                    "elapsed_s": round(el, 3),
                }
            )

        passed = sum(1 for r in results if r["passed"])
        pass_rate = (passed / len(results)) * 100.0 if results else 0.0
        g_rate = (sum(1 for r in results if r["checks"]["grounded"]) / len(results)) * 100.0
        gr_rate = (
            (
                sum(1 for r in results if r["checks"]["blocked"] and r["checks"]["urgent"])
                / len(results)
                * 100.0
            )
            if results
            else 0.0
        )
        summary = {
            "mode": mode,
            "total_cases": len(results),
            "passed_cases": passed,
            "pass_rate_pct": round(pass_rate, 1),
            "grounding_pass_rate_pct": round(g_rate, 1),
            "guardrail_accuracy_pct": round(gr_rate, 1),
            "average_latency_s": round(
                sum(r["elapsed_s"] for r in results) / max(1, len(results)), 3
            ),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cases": results,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0 if passed == len(results) else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["fake", "live"], default="fake")
    p.add_argument("--output", type=Path, default=REPORT)
    args = p.parse_args()
    return asyncio.run(run_eval(mode=args.mode, output_path=args.output))


if __name__ == "__main__":
    sys.exit(main())
