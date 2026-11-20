"""Pydantic v2 schemas for all HawaKhata API request and response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hawakhata.engine.aqi import GrapStage
from hawakhata.engine.planner import DayOutlook, DayPartSummary, MultiDaySlot, SafeFlushWindow


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseMeta(StrictBaseModel):
    request_id: str = Field(max_length=64)
    data_mode: Literal["live", "fixture"]
    engine_version: str = Field(default="0.1.0", max_length=20)
    constants_version: str = Field(default="v1", max_length=20)
    prompt_version: str = Field(default="v1.0", max_length=20)
    agent_version: str = Field(default="0.1.0", max_length=20)
    degraded: bool = False


class Envelope[T](StrictBaseModel):
    data: T
    meta: ResponseMeta


class LocationInput(StrictBaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    city_name: str | None = Field(default=None, max_length=100)


class ScheduleBlockInput(StrictBaseModel):
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    micro_env: str = Field(max_length=50)
    activity: str = Field(max_length=50)
    label: str = Field(default="", max_length=100)
    flexible: bool = False
    earliest_start: int | None = Field(default=None, ge=0, le=23)
    latest_end: int | None = Field(default=None, ge=1, le=24)


class MemberInput(StrictBaseModel):
    id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    age_band: str = Field(max_length=20)
    sensitivities: list[str] = Field(default_factory=list, max_length=10)
    schedule_blocks: list[ScheduleBlockInput] = Field(default_factory=list, max_length=24)


class RoomInput(StrictBaseModel):
    name: str = Field(max_length=50)
    volume_m3: float = Field(ge=5.0, le=500.0)
    purifier_cadr_m3_per_h: float = Field(default=0.0, ge=0.0, le=2000.0)
    windows_open_hours: list[int] = Field(default_factory=list, max_length=24)
    purifier_on_hours: list[int] = Field(default_factory=list, max_length=24)


class SourceEventInput(StrictBaseModel):
    kind: str = Field(max_length=50)
    start_hour: int = Field(ge=0, le=23)
    minutes: float = Field(default=60.0, ge=1.0, le=60.0)
    count: int = Field(default=1, ge=1, le=20)


class FamilyProfileInput(StrictBaseModel):
    id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    location: LocationInput
    members: list[MemberInput] = Field(min_length=1, max_length=20)
    rooms: list[RoomInput] = Field(default_factory=list, max_length=10)
    sources: list[SourceEventInput] = Field(default_factory=list, max_length=20)


class FlexibleActivityInput(StrictBaseModel):
    id: str = Field(max_length=50)
    member_id: str = Field(max_length=50)
    title: str = Field(max_length=100)
    duration_hours: int = Field(ge=1, le=4)
    earliest_start_hour: int = Field(ge=0, le=23)
    latest_start_hour: int = Field(ge=0, le=23)
    micro_env: str = Field(default="outdoor", max_length=50)
    activity: str = Field(default="moderate", max_length=50)
    usual_start_hour: int = Field(ge=0, le=23)


class BaseComputeRequest(StrictBaseModel):
    now: str | None = Field(default=None, max_length=35)
    data_source: Literal["auto", "fixture"] = "auto"


class ForecastRequest(StrictBaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    hours: int = Field(default=24, ge=1, le=96)
    language_code: str = Field(default="en", max_length=5)


class WeatherSummary(StrictBaseModel):
    temperature_c: float
    humidity_pct: float
    wind_speed_kmh: float
    precipitation_mm: float
    boundary_layer_height_m: float
    dispersion_regime: str
    physical_explanation: str


class FourDayForecastResponse(StrictBaseModel):
    city: str
    tomorrow_watch_headline: str
    tomorrow_watch_direction: Literal["worsens", "improves", "stable"]
    days: list[DayOutlook] = Field(min_length=4, max_length=4)
    safe_house_flush: SafeFlushWindow
    top_slots: list[MultiDaySlot] = Field(default_factory=list, max_length=3)
    current_weather: WeatherSummary | None = None
    # Current live AQ snapshot — same source as passbook endpoint
    current_aqi: int = 317
    current_pm25: float = 150.0
    current_category: str = "very_poor"
    current_category_label: str = "Very Poor"
    current_pm10: float | None = None
    data_mode: str = "fixture"
    data_source: str = Field(default="Offline Synthetic Fixture", max_length=60)
    fetched_at_ist: str = Field(default="", max_length=12)
    grap: GrapStage | None = None
    day_parts: list[DayPartSummary] = Field(default_factory=list, max_length=3)
    # Clock-aligned: index h is local clock hour h (next upcoming reading).
    hourly_pm25_24h: list[float] = Field(default_factory=list, max_length=24)


class MaskedActivityRequest(StrictBaseModel):
    location: LocationInput
    age_band: str = Field(default="31_41", max_length=20)
    activity: str = Field(default="walk", max_length=50)
    duration_min: int = Field(default=60, ge=10, le=240)
    start_hour: int = Field(default=7, ge=0, le=23)
    mask: Literal["none", "surgical", "n95"] = "none"


class LocationResult(StrictBaseModel):
    name: str = Field(max_length=120)
    admin1: str = Field(default="", max_length=120)
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    source: Literal["open_meteo_geocoding", "builtin"]


class PassbookRequest(BaseComputeRequest):
    profile: FamilyProfileInput


class PlanRequest(BaseComputeRequest):
    profile: FamilyProfileInput
    member_id: str = Field(max_length=50)
    flexible_activities: list[FlexibleActivityInput] = Field(max_length=10)


class IndoorSimulateRequest(BaseComputeRequest):
    room: RoomInput
    sources: list[SourceEventInput] = Field(default_factory=list, max_length=20)
    location: LocationInput


class PetGuidanceRequest(BaseComputeRequest):
    species: str = Field(default="dog", max_length=50)
    location: LocationInput = Field(
        default_factory=lambda: LocationInput(lat=28.4595, lng=77.0266, city_name="Delhi NCR")
    )


class SwapsImpactRequest(StrictBaseModel):
    swap_id: str = Field(max_length=50)
    units_per_day: float = Field(ge=0.0, le=1000.0)
    days_per_week: int = Field(default=5, ge=1, le=7)
    households: int = Field(default=1, ge=1, le=100_000)
    participation_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    location: LocationInput | None = None
    now: str | None = Field(default=None, max_length=35)


class BriefAction(StrictBaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=300)
    ug_saved: float = Field(ge=0.0)
    action_type: Literal["indoor_hack", "planner_window", "swap"]


class SensitiveAlert(StrictBaseModel):
    member_id: str = Field(max_length=64)
    name: str = Field(max_length=80)
    alert_text: str = Field(max_length=300)
    severity: Literal["advisory", "warning", "critical"]


class ForecastShiftInfo(StrictBaseModel):
    shifted: bool
    delta_max_pm25: float
    replanned: bool
    note: str = Field(max_length=300)


class BriefResponse(StrictBaseModel):
    headline: str = Field(max_length=200)
    worst_hour_local: str = Field(max_length=10)
    worst_pm25: float
    cleanest_window_local: str = Field(max_length=20)
    cleanest_pm25: float
    sensitive_member_alerts: list[SensitiveAlert]
    top_actions: list[BriefAction]
    forecast_shift: ForecastShiftInfo | None = None
    explanation: dict[str, Any]


class BriefRequest(BaseComputeRequest):
    profile: FamilyProfileInput
    previous_forecast_pm25: list[float] | None = Field(default=None, max_length=96)


class ChatMessageInput(StrictBaseModel):
    role: Literal["user", "model", "system"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseComputeRequest):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessageInput] = Field(default_factory=list, max_length=20)
    profile: FamilyProfileInput | None = None
    location: LocationInput | None = None
    language: str = Field(default="en", max_length=5)


class ChatResponse(StrictBaseModel):
    session_id: str = Field(max_length=64)
    reply: str = Field(max_length=5000)
    language: str = Field(default="en", max_length=5)
    numbers_used: list[float] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    follow_up: str | None = Field(default=None, max_length=500)
    chips: list[str] = Field(default_factory=list, max_length=10)
    grounded: bool = True
    degraded: bool = False


class MetaResponse(StrictBaseModel):
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
