from __future__ import annotations

import pytest
from pydantic import ValidationError

from hawakhata.api.schemas import (
    Envelope,
    FamilyProfileInput,
    LocationInput,
    MemberInput,
    PassbookRequest,
    ResponseMeta,
    RoomInput,
    ScheduleBlockInput,
    SwapsImpactRequest,
)


def test_location_bounds() -> None:
    loc = LocationInput(lat=28.46, lng=77.03)
    assert loc.lat == 28.46 and loc.lng == 77.03
    with pytest.raises(ValidationError):
        LocationInput(lat=95.0, lng=77.03)
    with pytest.raises(ValidationError):
        LocationInput(lat=28.46, lng=77.03, unknown_field="foo")  # type: ignore[call-arg]


def test_member_and_schedule_bounds() -> None:
    block = ScheduleBlockInput(
        start_hour=8, end_hour=17, micro_env="indoor_other", activity="sedentary", label="Office"
    )
    member = MemberInput(id="m1", name="Aarav", age_band="31_41", schedule_blocks=[block])
    assert member.name == "Aarav" and len(member.schedule_blocks) == 1
    with pytest.raises(ValidationError):
        ScheduleBlockInput(start_hour=8, end_hour=25, micro_env="outdoor", activity="light")


def test_room_input_bounds() -> None:
    room = RoomInput(name="Living Room", volume_m3=45.0, purifier_cadr_m3_per_h=250.0)
    assert room.volume_m3 == 45.0
    with pytest.raises(ValidationError):
        RoomInput(name="Tiny", volume_m3=1.0)


def test_envelope_structure() -> None:
    meta = ResponseMeta(request_id="req-123", data_mode="fixture")
    env = Envelope(data={"status": "ok"}, meta=meta)
    assert (
        env.data["status"] == "ok"
        and env.meta.request_id == "req-123"
        and env.meta.data_mode == "fixture"
    )


def test_passbook_request_validation() -> None:
    prof = FamilyProfileInput(
        id="fam1",
        name="Test Family",
        location=LocationInput(lat=28.46, lng=77.03),
        members=[MemberInput(id="m1", name="Dad", age_band="31_41")],
    )
    req = PassbookRequest(profile=prof)
    assert req.profile.name == "Test Family" and req.data_source == "auto"


def test_swaps_request_bounds() -> None:
    req = SwapsImpactRequest(
        swap_id="commute_car_to_metro",
        units_per_day=20.0,
        days_per_week=5,
        households=100,
        participation_rate=0.8,
    )
    assert req.participation_rate == 0.8
    with pytest.raises(ValidationError):
        SwapsImpactRequest(
            swap_id="commute_car_to_metro", units_per_day=20.0, participation_rate=1.5
        )
