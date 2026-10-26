"""All Docling imports and external document types stay inside this adapter."""

from importlib.metadata import version
from io import BytesIO
from pathlib import Path

from backend.core.documents import (
    DocumentBlock,
    PageGeometry,
    ParsedContent,
    SourceLocation,
    TableCell,
)
from backend.core.errors import DomainError


def prepare_native_runtime():
    # Windows BLAS DLL initialization can stall when first loaded by the parsing
    # thread after the server starts. Initialize these libraries on the main thread.
    import numpy  # noqa: F401
    import scipy.linalg  # noqa: F401


def normalized_box(box, width, height):
    if width <= 0 or height <= 0:
        return None
    top_box = box.to_top_left_origin(page_height=height)
    left, right = sorted([top_box.l / width, top_box.r / width])
    top, bottom = sorted([top_box.t / height, top_box.b / height])
    left, top, right, bottom = [max(0.0, min(1.0, value)) for value in (left, top, right, bottom)]
    return (left, top, right - left, bottom - top)


class DoclingAdapter:
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir
        self._converters = {}

    @property
    def version(self):
        return f"{version('docling')}/litextract-3-pdfium-text"

    def _converter(self, ocr):
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        if ocr not in self._converters:
            options = PdfPipelineOptions(
                do_ocr=ocr,
                do_table_structure=True,
                enable_remote_services=False,
                allow_external_plugins=False,
                accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=4),
                document_timeout=300,
            )
            if ocr:
                options.ocr_options = EasyOcrOptions(lang=["en", "ch_sim"], use_gpu=False)
            if self.model_dir and self.model_dir.is_dir():
                options.artifacts_path = self.model_dir
            self._converters[ocr] = DocumentConverter(
                allowed_formats=[
                    InputFormat.PDF,
                    InputFormat.CSV,
                    InputFormat.XLSX,
                    InputFormat.DOCX,
                ],
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=options, backend=PyPdfiumDocumentBackend
                    )
                },
            )
        return self._converters[ocr]

    def parse(self, data: bytes, asset: dict, ocr=False) -> ParsedContent:
        from docling.datamodel.base_models import DocumentStream

        stream = DocumentStream(name=Path(asset["relative_path"]).name, stream=BytesIO(data))
        result = self._converter(ocr).convert(stream, raises_on_error=True)
        status = str(getattr(result.status, "value", result.status))
        if status not in {"success", "partial_success"}:
            raise DomainError("文档转换没有成功完成，请检查文件是否损坏或加密。")
        document = result.document
        is_pdf = asset["kind"] == "pdf"
        pages = (
            [
                PageGeometry(number=number, width=page.size.width, height=page.size.height)
                for number, page in sorted(document.pages.items())
            ]
            if is_pdf
            else []
        )
        sizes = {page.number: page for page in pages}
        blocks = []
        section = ""
        for item, depth in document.iterate_items():
            label = str(getattr(item.label, "value", item.label))
            text = getattr(item, "text", "") or ""
            kind = "heading" if label in {"title", "section_header"} else "text"
            if label == "table":
                kind = "table"
                text = item.caption_text(document)
            elif label == "picture":
                kind = "picture"
                text = item.caption_text(document)
            if not text and kind not in {"table", "picture"}:
                continue
            if kind == "heading":
                section = text
            locations = []
            for provenance in getattr(item, "prov", []) if is_pdf else []:
                page = sizes.get(provenance.page_no)
                box = normalized_box(provenance.bbox, page.width, page.height) if page else None
                locations.append(SourceLocation(page=provenance.page_no, bbox=box))
            block = DocumentBlock(
                id=item.self_ref,
                kind=kind,
                text=text,
                label=label,
                level=getattr(item, "level", depth),
                section=section,
                locations=locations,
            )
            if kind == "table":
                block.rows, block.columns = item.data.num_rows, item.data.num_cols
                block.cells = [
                    TableCell(
                        text=cell.text,
                        row=cell.start_row_offset_idx,
                        column=cell.start_col_offset_idx,
                        row_span=cell.row_span,
                        column_span=cell.col_span,
                        header=cell.column_header or cell.row_header,
                    )
                    for cell in item.data.table_cells
                ]
            blocks.append(block)
        warnings = []
        if is_pdf:
            from backend.parsers.pdf_text import NOTICE, supplement_pdf_text

            additions = supplement_pdf_text(data, blocks)
            blocks.extend(additions)
            if additions:
                warnings.append(NOTICE)
        if status == "partial_success":
            warnings.append("部分内容未能解析完整，请结合原文复核。")
        if not blocks:
            warnings.append("未识别到正文或表格；若为扫描 PDF，请启用扫描页文字识别后重试。")
        if not is_pdf:
            warnings.append("此格式没有可靠的原始 PDF 页码；按段落或表格定位，不生成虚构页码。")
        if is_pdf and not ocr:
            warnings.append("当前读取 PDF 文字层；图片内文字需要启用扫描页文字识别。")
        return ParsedContent(
            parser_version=self.version,
            source_sha256=asset["sha256"],
            asset_id=asset["id"],
            filename=asset["relative_path"],
            pages=pages,
            blocks=blocks,
            warnings=warnings,
        )
