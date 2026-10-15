import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen.canvas import Canvas

from backend.parsers.docling_adapter import DoclingAdapter
from scripts.create_reading_fixtures import create_fixtures


@pytest.fixture(scope="module")
def documents(tmp_path_factory):
    directory = tmp_path_factory.mktemp("reading")
    create_fixtures(directory)
    return directory, DoclingAdapter(Path(".local/docling-models"))


@pytest.mark.parametrize("kind", ["empty", "corrupt", "encrypted"])
def test_abnormal_pdf_is_rejected_without_results(documents, kind):
    from docling.exceptions import ConversionError

    _, parser = documents
    data = b"" if kind == "empty" else b"%PDF-1.4\nbroken document"
    if kind == "encrypted":
        buffer = BytesIO()
        canvas = Canvas(buffer, encrypt=StandardEncryption("test-password"))
        canvas.drawString(40, 700, "Encrypted literature")
        canvas.save()
        data = buffer.getvalue()
    with pytest.raises(ConversionError):
        parser.parse(
            data,
            {
                "relative_path": "abnormal.pdf",
                "id": "abnormal",
                "sha256": hashlib.sha256(data).hexdigest(),
                "kind": "pdf",
            },
        )


@pytest.mark.parametrize("name", ["paper.pdf", "supp.csv", "supp.xlsx", "supp.docx", "scanned.pdf"])
def test_real_docling_formats_and_evidence(documents, name):
    directory, parser = documents
    data = (directory / name).read_bytes()
    result = parser.parse(
        data,
        {
            "relative_path": name,
            "id": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "kind": name.split(".")[-1],
        },
        ocr=name == "scanned.pdf",
    )
    text = " ".join(
        [block.text + " ".join(cell.text for cell in block.cells) for block in result.blocks]
    )
    assert "Alpha" in text, text
    assert "12.5" in text, text
    if name == "scanned.pdf":
        assert "河流" in text, text
    if name.endswith("pdf"):
        assert result.pages
        positions = [location for block in result.blocks for location in block.locations]
        assert positions
        assert all(
            location.bbox and all(0 <= n <= 1 for n in location.bbox) for location in positions
        )
        if name == "paper.pdf":
            evidence = next(
                block for block in result.blocks if "observed concentration" in block.text
            )
            assert evidence.locations[0].page == 2
            assert any(block.kind == "table" and block.rows >= 3 for block in result.blocks)
    else:
        assert result.pages == []
        assert all(not block.locations for block in result.blocks)
        assert any(block.kind == "table" for block in result.blocks)
