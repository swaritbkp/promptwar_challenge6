"""Pydantic v2 schemas for all HawaKhata API request and response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model forbidding extra fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseMeta(StrictBaseModel):
    """Standard metadata container for 2xx responses."""

    request_id: str = Field(max_length=64)
    data_mode: Literal["live", "fixture"]
    engine_version: str = Field(default="0.1.0", max_length=20)
    constants_version: str = Field(default="v1", max_length=20)
    prompt_version: str = Field(default="v1.0", max_length=20)
    agent_version: str = Field(default="0.1.0", max_length=20)
    degraded: bool = False


class Envelope[T](StrictBaseModel):
    """Unified 2xx JSON response envelope."""

    data: T
    meta: ResponseMeta


class LocationInput(StrictBaseModel):
    """Geographic coordinate specification."""

    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    city_name: str | None = Field(default=None, max_length=100)


class ScheduleBlockInput(StrictBaseModel):
    """Contiguous block of member activity in a schedule."""

    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    micro_env: str = Field(max_length=50)
    activity: str = Field(max_length=50)
    label: str = Field(default="", max_length=100)
    flexible: bool = False
    earliest_start: int | None = Field(default=None, ge=0, le=23)
    latest_end: int | None = Field(default=None, ge=1, le=24)


class MemberInput(StrictBaseModel):
    """Family member profile input."""

    id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    age_band: str = Field(max_length=20)
    sensitivities: list[str] = Field(default_factory=list, max_length=10)
    schedule_blocks: list[ScheduleBlockInput] = Field(default_factory=list, max_length=24)


class RoomInput(StrictBaseModel):
    """Living zone specification for indoor simulation."""

    name: str = Field(max_length=50)
    volume_m3: float = Field(ge=5.0, le=500.0)
    purifier_cadr_m3_per_h: float = Field(default=0.0, ge=0.0, le=2000.0)
    windows_open_hours: list[int] = Field(default_factory=list, max_length=24)
    purifier_on_hours: list[int] = Field(default_factory=list, max_length=24)


class SourceEventInput(StrictBaseModel):
    """Indoor particulate emission event."""

    kind: str = Field(max_length=50)
    start_hour: int = Field(ge=0, le=23)
    minutes: float = Field(default=60.0, ge=1.0, le=60.0)
    count: int = Field(default=1, ge=1, le=20)


class FamilyProfileInput(StrictBaseModel):
    """Complete household profile schema."""

    id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    location: LocationInput
    members: list[MemberInput] = Field(min_length=1, max_length=20)
    rooms: list[RoomInput] = Field(default_factory=list, max_length=10)
    sources: list[SourceEventInput] = Field(default_factory=list, max_length=20)


class FlexibleActivityInput(StrictBaseModel):
    """Activity candidate for clean-window optimization."""

    id: str = Field(max_length=50)
    member_id: str = Field(max_length=50)
    title: str = Field(max_length=100)
    duration_hours: int = Field(ge=1, le=4)
    earliest_start_hour: int = Field(ge=0, le=23)
    latest_start_hour: int = Field(ge=0, le=23)
    micro_env: str = Field(default="outdoor", max_length=50)
    activity: str = Field(default="moderate", max_length=50)
    usual_start_hour: int = Field(ge=0, le=23)


class ForecastRequest(StrictBaseModel):
    """Request payload for hourly air forecast."""

    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    hours: int = Field(default=24, ge=1, le=96)
    language_code: str = Field(default="en", max_length=5)


class PassbookRequest(StrictBaseModel):
    """Request payload for multi-member family air passbook."""

    profile: FamilyProfileInput
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class PlanRequest(StrictBaseModel):
    """Request payload for clean-window optimization."""

    profile: FamilyProfileInput
    member_id: str = Field(max_length=50)
    flexible_activities: list[FlexibleActivityInput] = Field(max_length=10)
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class IndoorSimulateRequest(StrictBaseModel):
    """Request payload for indoor PM2.5 simulation."""

    room: RoomInput
    sources: list[SourceEventInput] = Field(default_factory=list, max_length=20)
    location: LocationInput
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class SwapsImpactRequest(StrictBaseModel):
    """Request payload for sustainable alternatives."""

    swap_id: str = Field(max_length=50)
    units_per_day: float = Field(ge=0.0, le=1000.0)
    days_per_week: int = Field(default=5, ge=1, le=7)
    households: int = Field(default=1, ge=1, le=100_000)
    participation_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    location: LocationInput | None = None
    now: str | None = Field(default=None, max_length=35)


class BriefAction(StrictBaseModel):
    """Actionable recommendation with quantified exposure savings."""

    title: str = Field(max_length=120)
    description: str = Field(max_length=300)
    ug_saved: float = Field(ge=0.0)
    action_type: Literal["indoor_hack", "planner_window", "swap"]


class SensitiveAlert(StrictBaseModel):
    """Targeted alert for a vulnerable family member."""

    member_id: str = Field(max_length=64)
    name: str = Field(max_length=80)
    alert_text: str = Field(max_length=300)
    severity: Literal["advisory", "warning", "critical"]


class ForecastShiftInfo(StrictBaseModel):
    """Forecast shift detection outcome."""

    shifted: bool
    delta_max_pm25: float
    replanned: bool
    note: str = Field(max_length=300)


class BriefResponse(StrictBaseModel):
    """Proactive morning brief response payload."""

    headline: str = Field(max_length=200)
    worst_hour_local: str = Field(max_length=10)
    worst_pm25: float
    cleanest_window_local: str = Field(max_length=20)
    cleanest_pm25: float
    sensitive_member_alerts: list[SensitiveAlert]
    top_actions: list[BriefAction]
    forecast_shift: ForecastShiftInfo | None = None
    explanation: dict[str, Any]


class BriefRequest(StrictBaseModel):
    """Request payload for morning proactive brief."""

    profile: FamilyProfileInput
    previous_forecast_pm25: list[float] | None = Field(default=None, max_length=96)
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class ChatMessageInput(StrictBaseModel):
    """Turn in a multi-turn conversation."""

    role: Literal["user", "model", "system"]
    content: str = Field(max_length=4000)


class ChatRequest(StrictBaseModel):
    """Request payload for Ask HawaKhata chat endpoint."""

    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessageInput] = Field(default_factory=list, max_length=20)
    profile: FamilyProfileInput | None = None
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class MetaResponse(StrictBaseModel):
    """System version and runtime metadata."""

    app_name: str
    app_version: str
    engine_version: str
    constants_version: str
    prompt_version: str
    agent_version: str
    data_mode: Literal["live", "fixture"]
    has_live_air_data: bool
    has_llm: bool
    gemini_primary_model: str
    gemini_fallback_model: str
    env: str
