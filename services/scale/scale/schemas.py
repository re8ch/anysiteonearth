from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AnalysisStatus(str, Enum):
    queued = "queued"
    acquiring = "acquiring"
    processing = "processing"
    inferencing = "inferencing"
    completed = "completed"
    failed = "failed"


class Activity(str, Enum):
    hiking = "hiking"
    gravel_bike = "gravel_bike"
    passenger_car = "passenger_car"
    four_wheel_drive = "four_wheel_drive"


class AnalysisProduct(str, Enum):
    road_scores = "road_scores"
    candidate_corridors = "candidate_corridors"
    scenic_loops = "scenic_loops"


class CandidateMode(str, Enum):
    conservative = "conservative"
    exploratory = "exploratory"


class RoutePreferences(BaseModel):
    activities: list[Activity] = Field(
        default_factory=lambda: [Activity.hiking, Activity.gravel_bike], min_length=1
    )
    min_distance_km: float = Field(default=8, ge=1, le=100)
    max_distance_km: float = Field(default=25, ge=1, le=150)
    max_slope: float = Field(default=0.35, ge=0.02, le=1)
    allow_inferred: bool = True

    @model_validator(mode="after")
    def ordered(self) -> "RoutePreferences":
        if self.min_distance_km >= self.max_distance_km:
            raise ValueError("route_preferences min_distance_km must be below max_distance_km")
        return self


class BBox(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def ordered(self) -> "BBox":
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("bbox must satisfy west < east and south < north")
        return self


class TimeWindow(BaseModel):
    start: date = Field(default_factory=lambda: date.today() - timedelta(days=180))
    end: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def ordered(self) -> "TimeWindow":
        if self.start >= self.end:
            raise ValueError("time_window.start must be before end")
        if (self.end - self.start).days > 730:
            raise ValueError("time window cannot exceed 730 days")
        return self


class AnalysisCreate(BaseModel):
    bbox: BBox
    activities: list[Activity] = Field(default_factory=lambda: list(Activity), min_length=1)
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    model_version: str | None = None
    products: list[AnalysisProduct] = Field(default_factory=lambda: list(AnalysisProduct))
    candidate_mode: CandidateMode = CandidateMode.exploratory
    route_preferences: RoutePreferences = Field(default_factory=RoutePreferences)


class AnalysisAccepted(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    stage: str


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AnalysisView(AnalysisAccepted):
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    error: ErrorBody | None = None


class Evidence(BaseModel):
    source: str
    observed_at: str | None = None
    native_resolution_m: float | None = None
    license: str
    quality: float = Field(ge=0, le=1)


class FeedbackCreate(BaseModel):
    analysis_id: UUID
    segment_id: str | None = None
    target_type: Literal["road_segment", "candidate_corridor", "scenic_loop"] = "road_segment"
    target_id: str | None = None
    exists: bool | None = None
    surface_class: str | None = None
    passable_by: list[Activity] = Field(default_factory=list)
    obstacle: str | None = Field(default=None, max_length=500)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    gps_trace_summary: dict[str, Any] | None = None
    visibility: Literal["private", "public"] = "private"

    @model_validator(mode="after")
    def target_present(self) -> "FeedbackCreate":
        if not (self.target_id or self.segment_id):
            raise ValueError("target_id or segment_id is required")
        if self.target_id is None:
            self.target_id = self.segment_id
        return self


class GpsTraceCreate(BaseModel):
    analysis_id: UUID
    target_type: Literal["road_segment", "candidate_corridor", "scenic_loop"] = "candidate_corridor"
    target_id: str
    geometry: dict[str, Any]
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    observer_id: str | None = Field(default=None, max_length=200)
    visibility: Literal["private", "public"] = "private"

    @model_validator(mode="after")
    def valid_geometry(self) -> "GpsTraceCreate":
        if self.geometry.get("type") != "LineString":
            raise ValueError("GPS geometry must be a GeoJSON LineString")
        coordinates = self.geometry.get("coordinates") or []
        if not 2 <= len(coordinates) <= 20_000:
            raise ValueError("GPS trace must contain 2 to 20,000 points")
        if any(not isinstance(point, list) or len(point) < 2 for point in coordinates):
            raise ValueError("GPS coordinates are invalid")
        return self


class GpsTraceAccepted(BaseModel):
    trace_id: UUID
    verification_state: Literal["unmatched", "gps_supported", "verified"]
    mean_distance_m: float | None = None
    coverage: float = 0


class FeedbackAccepted(BaseModel):
    feedback_id: UUID
    visibility: Literal["private", "public"]


class ModelInfo(BaseModel):
    version: str
    production: bool
    kind: str
    training_data_version: str
    applicable_region: str
    limitations: list[str]
