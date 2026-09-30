from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Events may be up to 24h late (assignment rule). A few minutes of *future*
# skew is tolerated so a client whose clock runs slightly fast is not rejected.
MAX_LATE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)


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
        if value.tzinfo is None:
            raise ValueError("timestamp requires an offset")
        now = datetime.now(timezone.utc)
        value = value.astimezone(timezone.utc)
        if value > now + MAX_FUTURE_SKEW or value < now - MAX_LATE:
            raise ValueError("timestamp must be within the last 24 hours")
        return value


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID


class KeyCreated(BaseModel):
    id: UUID
    prefix: str
    secret: str


class KeyInfo(BaseModel):
    id: UUID
    prefix: str
    created_at: datetime
    revoked_at: datetime | None
    overlap_expires_at: datetime | None = None
