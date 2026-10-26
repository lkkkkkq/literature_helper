from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    type: Literal["string", "number", "boolean"] = "string"
    unit: str = Field(default="", max_length=80)
    minimum: float | None = None
    maximum: float | None = None


class ExtractionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    granularity: str = Field(min_length=1, max_length=1000)
    fields: list[FieldDefinition] = Field(min_length=1, max_length=50)
    plugins: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    record_key: list[str] = Field(min_length=1, max_length=10)
    missing_policy: Literal["null_with_reason"] = "null_with_reason"
    conflict_policy: Literal["keep_separate_and_flag"] = "keep_separate_and_flag"
    evidence_policy: Literal["quoted_source_required"] = "quoted_source_required"

    @model_validator(mode="after")
    def validate_fields(self):
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)) or not set(self.record_key).issubset(keys):
            raise ValueError("字段标识不可重复，记录标识必须引用已有字段")
        for field in self.fields:
            if (
                field.minimum is not None
                and field.maximum is not None
                and field.minimum > field.maximum
            ):
                raise ValueError("最小值不能大于最大值")
        return self


class DesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    goal: str = Field(min_length=1, max_length=10000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    fulltext_batch: int | None = Field(default=None, ge=1)


class ConfirmPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_id: UUID
    request_id: UUID
    plan: ExtractionPlan


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | float | bool | None
    unit: str = Field(default="", max_length=80)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    missing_reason: str = Field(default="", max_length=1000)
    standardized: dict | None = None


class ExtractedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, ExtractedField]
    risks: list[str] = Field(default_factory=list, max_length=30)


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[ExtractedRecord] = Field(max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=100)
