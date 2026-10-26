from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.documents import SourceLocation


class ModelProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=100)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        url = urlsplit(value)
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError("接口地址不能包含凭据、查询参数或片段")
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("远程接口必须使用 HTTPS，本机接口可使用 HTTP")
        return value.rstrip("/")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    question: str = Field(min_length=1, max_length=10000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=100)
    fulltext_batch: int | None = Field(default=None, ge=1)


class Evidence(BaseModel):
    id: str
    document_id: str
    asset_id: str
    filename: str
    source_sha256: str
    block_id: str
    quote: str
    locations: list[SourceLocation] = Field(default_factory=list)
    kind: str = "text"
    parse_version: str | None = None
    source_position: list[dict] = Field(default_factory=list)


class AnswerPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=12000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    kind: Literal["claim", "uncertainty"] = "claim"


class AnswerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: list[AnswerPart] = Field(min_length=1, max_length=30)
