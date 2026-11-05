from typing import Literal
import re
from urllib.parse import parse_qsl, urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InvestigationArea(BaseModel):
    """A research rectangle, not an official administrative boundary or sensor coverage."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    south: float = Field(29.75, ge=-85, le=85)
    west: float = Field(30.90, ge=-180, le=180)
    north: float = Field(30.35, ge=-85, le=85)
    east: float = Field(31.75, ge=-180, le=180)

    @model_validator(mode="after")
    def bounded(self):
        if not 0 < self.north - self.south <= 1 or not 0 < self.east - self.west <= 2:
            raise ValueError("Use an ordered regional bbox no larger than 1 degree latitude by 2 degrees longitude")
        return self


class CandidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field("operator", min_length=1, max_length=100)
    source_ref: str | None = Field(None, max_length=2000)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    @field_validator("source_ref")
    @classmethod
    def public_documentation(cls, value):
        if value is None:
            return value
        url = urlsplit(value)
        if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
            raise ValueError(
                "Use a public documentation URL without credentials; stream secrets belong in server variables"
            )
        if any(
            any(secret in key.lower() for secret in ("token", "key", "password", "signature"))
            for key, _ in parse_qsl(url.query)
        ):
            raise ValueError("Do not put credentials or signed URLs in the discovery registry")
        return value

    @model_validator(mode="after")
    def coords(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Both coordinates must be supplied, or both null")
        return self


class PermissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permission_state: Literal["unknown", "public_documented", "owner_authorized", "denied"]
    evidence: str | None = Field(None, max_length=4000)
    url_env: str | None = Field(None, pattern=r"^CAMERA_[A-Z0-9_]+_URL$")
    protocol: Literal["rtsp", "http", "hls", "onvif"] | None = None
    authorized: bool = False

    @field_validator("evidence")
    @classmethod
    def no_stream_credentials(cls, value):
        if value and re.search(r"(?:rtsps?|https?)://[^\s/]+@", value, re.IGNORECASE):
            raise ValueError("Keep credentialed stream URLs in server configuration, not permission notes")
        return value

    @model_validator(mode="after")
    def permission_basis(self):
        if self.permission_state in ("public_documented", "owner_authorized"):
            if not self.authorized or not self.evidence or len(self.evidence.strip()) < 10:
                raise ValueError("Explicit authorization and a recorded permission basis are required")
        return self


class IntegrateIn(BaseModel):
    authorized: Literal[True]
