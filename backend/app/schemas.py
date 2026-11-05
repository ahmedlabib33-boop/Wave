from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceType = Literal[
    "adsb",
    "traffic",
    "satellite",
    "camera",
    "ais",
    "environment",
    "phone",
    "radar",
    "rest",
    "mqtt",
    "serial",
    "websocket",
]
Method = Literal[
    "direct_measurement",
    "third_party_reported_position",
    "estimated_speed",
    "camera_frame_detection",
    "camera_ground_projection",
    "road_segment_report",
    "historical_satellite",
    "device_location",
    "environmental_reading",
]


class Area(BaseModel):
    latitude: float = Field(30.0878597, ge=-90, le=90)
    longitude: float = Field(31.3413867, ge=-180, le=180)
    radius_m: int = Field(5000, ge=1000, le=5000)


class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    object_type: str = Field(min_length=1, max_length=50)
    track_id: str | None = Field(None, max_length=150)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    altitude: float | None = None
    speed_mps: float | None = Field(None, ge=0, le=12000)
    heading_deg: float | None = Field(None, ge=0, lt=360)
    confidence: float | None = Field(None, ge=0, le=1)
    observed_at: datetime | None
    location_accuracy_m: float | None = Field(None, ge=0)
    measurement_method: Method
    details: dict = Field(default_factory=dict)
    raw: dict = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if value > datetime.now(timezone.utc) + timedelta(seconds=120):
            raise ValueError("observation is in the future (clock tolerance 120s)")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def measurement_basis(self):
        if self.observed_at is None and self.measurement_method != "road_segment_report":
            raise ValueError("This measurement requires an acquisition timestamp")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be provided or both null")
        if self.measurement_method == "camera_frame_detection" and (
            self.latitude is not None or self.speed_mps is not None
        ):
            raise ValueError("Uncalibrated frame detections cannot carry object coordinates or physical speed")
        if self.measurement_method in ("estimated_speed", "camera_ground_projection") and not self.details.get(
            "calibration_id"
        ):
            raise ValueError("Camera projection and speed estimates require a calibration_id")
        return self


class SourceIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["rest", "mqtt", "serial", "websocket", "phone", "radar"]
    coverage: str = Field("Unverified; supplied by operator", max_length=2000)


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url_env: str = Field(pattern=r"^CAMERA_[A-Z0-9_]+_URL$")
    protocol: Literal["rtsp", "http", "hls", "onvif"]
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    direction_deg: float | None = Field(None, ge=0, lt=360)
    fov_deg: float | None = Field(None, gt=0, le=360)
    authorized: Literal[True]

    @model_validator(mode="after")
    def coords(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Both camera coordinates must be supplied or both null")
        return self


class CalibrationIn(BaseModel):
    image_points: list[tuple[float, float]] = Field(min_length=4, max_length=50)
    ground_points_m: list[tuple[float, float]] = Field(min_length=4, max_length=50)
    image_width: int = Field(ge=64, le=16000)
    image_height: int = Field(ge=64, le=16000)
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    survey_error_m: float = Field(gt=0, le=100)
    validation_image_points: list[tuple[float, float]] = Field(min_length=2, max_length=50)
    validation_ground_points_m: list[tuple[float, float]] = Field(min_length=2, max_length=50)
    lens_corrected: Literal[True]
    pts_validated: bool = False
    timestamp_error_s: float | None = Field(None, gt=0, le=2)
    notes: str = Field(min_length=5, max_length=2000)
