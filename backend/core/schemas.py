from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(InputModel):
    name: Name
    source_path: str = Field(min_length=1, max_length=32768)


class Rename(InputModel):
    name: Name


class SessionCreate(InputModel):
    name: Name = "新会话"


class MessageCreate(InputModel):
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
    ]


class AssetSnapshot(BaseModel):
    relative_path: str
    absolute_path: str
    size: int
    mtime_ns: int
    sha256: str
    kind: str


class GroupSuggestion(BaseModel):
    key: str
    title: str
    main_path: str | None
    asset_paths: list[str]
    confidence: Literal["high", "review"]
    reason: str


class ScanSnapshot(BaseModel):
    assets: list[AssetSnapshot]
    groups: list[GroupSuggestion]
    warnings: list[str]


class GroupConfirm(InputModel):
    title: Name
    main_path: str | None = None
    asset_paths: list[str] = Field(min_length=1)


class ScanConfirm(InputModel):
    draft_id: str
    groups: list[GroupConfirm]
