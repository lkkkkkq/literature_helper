"""Recover text omitted by layout analysis; preserve the original page, not guessed LaTeX."""

import re

from backend.core.documents import DocumentBlock, SourceLocation

NOTICE = "PDF 文字层补充：公式上下标、分数与根号的顺序可能失真，请对照原页，不可据此猜补公式。"


def supplement_pdf_text(data, blocks):
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock

    existing = {}
    for block in blocks:
        for location in block.locations:
            existing.setdefault(location.page, []).append(
                block.text + " " + " ".join(cell.text for cell in block.cells)
            )
    additions = []
    with pypdfium2_lock, pdfium.PdfDocument(data) as document:
        for index in range(len(document)):
            page = document[index]
            textpage = None
            try:
                textpage = page.get_textpage()
                raw = textpage.get_text_range().strip()
            finally:
                if textpage is not None:
                    textpage.close()
                page.close()
            if not raw:
                continue
            # Compare character coverage rather than word order: layout can reorder text.
            known = "".join(existing.get(index + 1, []))
            if re.sub(r"\s+", "", raw) in re.sub(r"\s+", "", known):
                continue
            raw_tokens = set(re.findall(r"\w+|[^\w\s]", raw))
            known_tokens = set(re.findall(r"\w+|[^\w\s]", known))
            if not raw_tokens - known_tokens - {str(index + 1)}:
                continue
            additions.append(
                DocumentBlock(
                    id=f"pdf-text-page-{index + 1}",
                    kind="text",
                    label="pdf_text_fallback",
                    text=raw,
                    section=NOTICE,
                    locations=[SourceLocation(page=index + 1, bbox=(0, 0, 1, 1))],
                )
            )
    return additions
