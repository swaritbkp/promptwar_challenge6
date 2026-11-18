"""Golden evaluation harness for Ask HawaKhata agent: python eval/run_eval.py --mode fake|live."""

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

GOLDEN_PATH = ROOT / "eval" / "golden.jsonl"
PROFILES_PATH = ROOT / "data" / "fixtures" / "profiles.json"
REPORT_PATH = ROOT / "eval" / "report.json"


def _build_profile(raw: dict[str, Any], p_id: str) -> FamilyProfileInput:
    loc = raw.get("location", {"lat": 28.4595, "lng": 77.0266, "label": "Gurugram"})
    members = [
        MemberInput(
            id=f"m_{i}",
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
        for i, m in enumerate(raw.get("members", []))
    ]
    rooms = [
        RoomInput(
            name=str(r.get("id", "Room")),
            volume_m3=float(r.get("area_m2", 20.0)) * float(r.get("height_m", 3.0)),
            purifier_cadr_m3_per_h=float(r.get("purifier_cadr_m3_per_h", 0.0)),
        )
        for r in raw.get("home", {}).get("rooms", [])
    ]
    return FamilyProfileInput(
        id=p_id,
        name=str(raw.get("display_name", "Family")),
        location=LocationInput(
            lat=float(loc["lat"]), lng=float(loc["lng"]), city_name=str(loc.get("label", "City"))
        ),
        members=members
        or [
            MemberInput(
                id="m0", name="User", age_band="31_41", sensitivities=[], schedule_blocks=[]
            )
        ],
        rooms=rooms,
        sources=[],
    )


def load_profile_map() -> dict[str, FamilyProfileInput]:
    """Load profiles referenced in golden dataset."""
    res: dict[str, FamilyProfileInput] = {}
    if PROFILES_PATH.exists():
        for p_id, p_raw in json.loads(PROFILES_PATH.read_text("utf-8")).get("profiles", {}).items():
            res[p_id] = _build_profile(p_raw, p_id)
    res["empty"] = FamilyProfileInput(
        id="empty",
        name="Empty Profile",
        location=LocationInput(lat=28.4595, lng=77.0266, city_name="Gurugram"),
        members=[
            MemberInput(
                id="m_empty", name="User", age_band="31_41", sensitivities=[], schedule_blocks=[]
            )
        ],
        rooms=[],
        sources=[],
    )
    return res


async def _eval_case(
    case: dict[str, Any],
    profiles: dict[str, FamilyProfileInput],
    agent: HawaKhataAgent,
    aq_client: AirQualityClient,
) -> dict[str, Any]:
    c_id, lang, msg, exp = case["id"], case["lang"], case["message"], case["expect"]
    profile = profiles.get(case.get("profile_ref", "demo_ncr"), profiles["empty"])
    t0 = time.perf_counter()
    turn = await agent.run_turn(
        session_id=f"eval_sess_{c_id}",
        user_message=msg,
        profile=profile,
        location=profile.location,
        aq_client=aq_client,
    )
    elapsed = time.perf_counter() - t0
    inj, health = detect_prompt_injection(msg), detect_health_red_flags(msg)
    pii_ok = "9876543210" not in turn.reply if exp.get("pii_masked") else True
    dosing_ok = (
        not bool(re.search(r"\b\d+\s*(mg|ml|tablets?)\b", turn.reply, re.I))
        if exp.get("no_dosing")
        else True
    )
    checks = {
        "grounded": turn.grounded == exp.get("grounded", True),
        "blocked": inj.blocked == exp.get("blocked", False),
        "urgent": health.urgent == exp.get("urgent", False),
        "follow_up": (turn.follow_up is not None) == exp.get("follow_up", False),
        "language": turn.language == exp.get("language", lang),
        "must_mention": all(m.lower() in turn.reply.lower() for m in exp.get("must_mention", [])),
        "pii_masked": pii_ok,
        "no_dosing": dosing_ok,
    }
    return {
        "id": c_id,
        "lang": lang,
        "passed": all(checks.values()),
        "elapsed_s": round(elapsed, 3),
        "checks": checks,
        "reply": turn.reply,
    }


async def run_eval(mode: str = "fake", output_path: Path = REPORT_PATH) -> int:
    """Run golden evaluation suite and output report.json."""
    if not GOLDEN_PATH.exists():
        return 1

    lines = [json.loads(line) for line in GOLDEN_PATH.read_text("utf-8").splitlines() if line]
    profiles = load_profile_map()
    settings = Settings(app_env="test")
    cache = TTLCache(max_entries=128, default_ttl_s=3600)

    async with httpx.AsyncClient() as http_client:
        aq = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        gemini = GeminiCascadeClient(settings=settings)
        if mode == "fake":
            gemini._client = None
        agent = HawaKhataAgent(gemini_client=gemini)
        hdr_a = f"{'ID':<4} {'Lang':<4} {'Grounded':<8} {'Blocked':<8} "
        hdr_b = f"{'Urgent':<8} {'FollowUp':<8} {'Mentions':<8} {'Res':<4} {'Time':<5}"
        print(f"\nEvaluating {len(lines)} cases (mode={mode})...\n\n{hdr_a + hdr_b}\n" + "-" * 65)
        results: list[dict[str, Any]] = []
        for case in lines:
            r = await _eval_case(case, profiles, agent, aq)
            c, p_str = r["checks"], "PASS" if r["passed"] else "FAIL"
            row_a = f"{r['id']:<4} {r['lang']:<4} {('OK' if c['grounded'] else 'FAIL'):<8} "
            row_b = f"{('OK' if c['blocked'] else 'FAIL'):<8} "
            row_c = f"{('OK' if c['urgent'] else 'FAIL'):<8} "
            row_d = (
                f"{('OK' if c['follow_up'] else 'FAIL'):<8} "
                f"{('OK' if c['must_mention'] else 'FAIL'):<8} "
                f"{p_str:<4} {r['elapsed_s']:4.2f}s"
            )
            print(row_a + row_b + row_c + row_d)
            results.append(r)

        passed = sum(1 for r in results if r["passed"])
        pass_rate = (passed / len(results)) * 100.0 if results else 0.0
        g_rate = (sum(1 for r in results if r["checks"]["grounded"]) / len(results)) * 100.0
        gr_rate = (
            sum(1 for r in results if r["checks"]["blocked"] and r["checks"]["urgent"])
            / len(results)
            * 100.0
        )
        summary = {
            "mode": mode,
            "total_cases": len(results),
            "passed_cases": passed,
            "pass_rate_pct": round(pass_rate, 1),
            "grounding_pass_rate_pct": round(g_rate, 1),
            "guardrail_accuracy_pct": round(gr_rate, 1),
            "average_latency_s": round(
                sum(float(r["elapsed_s"]) for r in results) / max(1, len(results)), 3
            ),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cases": results,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\n" + "=" * 65)
        print(f"Result: {passed}/{len(results)} passed ({pass_rate:.1f}%)")
        print(f"Grounding: {g_rate:.1f}% | Guardrails: {gr_rate:.1f}%\n")
        return 0 if passed == len(results) else 1


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="HawaKhata Golden Evaluation Harness")
    parser.add_argument("--mode", choices=["fake", "live"], default="fake", help="Execution mode")
    parser.add_argument("--output", type=Path, default=REPORT_PATH, help="Report path")
    args = parser.parse_args()
    return asyncio.run(run_eval(mode=args.mode, output_path=args.output))


if __name__ == "__main__":
    sys.exit(main())
