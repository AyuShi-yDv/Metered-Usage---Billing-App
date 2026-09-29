from datetime import datetime, timezone, timedelta
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, ConfigDict

class UsageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    endpoint: str = Field(min_length=1, max_length=256, pattern=r"^/[A-Za-z0-9_./{}-]*$")
    timestamp: datetime
    duration_ms: int = Field(ge=0, le=3_600_000, strict=True)
    status_code: int = Field(ge=100, le=599, strict=True)
    @field_validator("timestamp")
    @classmethod
    def accepted_window(cls, value: datetime) -> datetime:
        if value.tzinfo is None: raise ValueError("timestamp requires an offset")
        now = datetime.now(timezone.utc)
        value = value.astimezone(timezone.utc)
        if value > now or value < now - timedelta(hours=24): raise ValueError("timestamp must be within the last 24 hours")
        return value

class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
class KeyCreated(BaseModel): id: UUID; prefix: str; secret: str
class KeyInfo(BaseModel): id: UUID; prefix: str; created_at: datetime; revoked_at: datetime | None
