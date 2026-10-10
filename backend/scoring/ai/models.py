"""Internal extracted features, without scores or model contributions."""

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import SignalGroup


class ExtractedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: str
    group: SignalGroup
    label_vi: str
    value: str | float | int | bool
