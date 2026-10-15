from typing import Literal

from pydantic import BaseModel, Field

from backend.core.schemas import InputModel


class ParseRequest(InputModel):
    ocr: bool = False
    force: bool = False


class PageGeometry(BaseModel):
    number: int
    width: float
    height: float


class SourceLocation(BaseModel):
    page: int = Field(ge=1)
    # Normalized top-left coordinates, independent of viewer zoom.
    bbox: tuple[float, float, float, float] | None = None


class TableCell(BaseModel):
    text: str
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    header: bool = False


class DocumentBlock(BaseModel):
    id: str
    kind: Literal["heading", "text", "table", "picture"]
    text: str
    label: str
    level: int = 0
    section: str = ""
    locations: list[SourceLocation] = []
    cells: list[TableCell] = []
    rows: int = 0
    columns: int = 0


class ParsedContent(BaseModel):
    format_version: int = 1
    parser: str = "docling"
    parser_version: str
    source_sha256: str
    asset_id: str
    filename: str
    pages: list[PageGeometry] = []
    blocks: list[DocumentBlock] = []
    warnings: list[str] = []
