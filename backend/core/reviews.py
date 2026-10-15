from pydantic import BaseModel, ConfigDict, Field

from backend.core.extraction import ExtractedField


class ReviewEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: int = Field(ge=0)
    record_id: str
    field_key: str
    after: ExtractedField
    reason: str = Field(min_length=1, max_length=2000)
