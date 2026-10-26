from io import BytesIO

from reportlab.pdfgen import canvas

from backend.core.chat import Evidence
from backend.core.documents import DocumentBlock, SourceLocation
from backend.parsers.pdf_text import supplement_pdf_text
from backend.tools.retrieval import retrieve


def source(index, text, page=1, asset="a"):
    return Evidence(
        id=str(index),
        document_id="d",
        asset_id=asset,
        filename="paper.pdf",
        source_sha256="sha",
        block_id=str(index),
        quote=text,
        locations=[SourceLocation(page=page)],
    )


def test_bilingual_formula_search_and_budget():
    items = [source(i, f"Unrelated introduction {i}", i + 1) for i in range(50)]
    items += [
        source(100, "The induced power, profile power and parasite power", 47),
        source(101, "Model Summary Pi(T, Vz) Pp(T, Vair) Ppar(Vair) (3.8)", 48),
    ]
    for query in ["诱导功率、剖面功率、寄生功率三个分量", "Pi Pp Ppar", "三种功率的公式"]:
        result = retrieve(query, items)
        assert any(item.id == "101" for item in result)
        assert len(result) <= 32
        assert sum(len(item.quote) for item in result) <= 48000
    assert sum(len(item.quote) for item in retrieve("功率公式", items, budget=80)) <= 80
    assert retrieve("zzzznonexistent", items) == []
    assert retrieve("功率", items, budget=0) == []


def test_pdf_text_recovers_omitted_formula_without_inventing_latex():
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 700, "Power model summary")
    pdf.drawString(72, 650, "Ppar(Vair) = c4 Vair3 (3.8)")
    pdf.save()
    blocks = [
        DocumentBlock(
            id="summary",
            kind="text",
            label="text",
            text="Power model summary",
            locations=[SourceLocation(page=1)],
        )
    ]
    recovered = supplement_pdf_text(stream.getvalue(), blocks)
    assert len(recovered) == 1
    assert "Ppar(Vair) = c4 Vair3 (3.8)" in recovered[0].text
    assert recovered[0].locations[0].page == 1
    assert recovered[0].locations[0].bbox == (0, 0, 1, 1)
    assert "可能失真" in recovered[0].section
    assert supplement_pdf_text(stream.getvalue(), blocks + recovered) == []


def test_legacy_cache_gets_read_only_text_supplement(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from backend.core.documents import ParsedContent
    from backend.services.reading import ReadingService

    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 700, "Ppar(Vair) = c4 Vair3 (3.8)")
    pdf.save()
    cached = ParsedContent(
        parser_version="2.135/litextract-2-pdfium",
        source_sha256="sha",
        asset_id="a",
        filename="paper.pdf",
    )
    path = tmp_path / "old.json"
    path.write_text(cached.model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    repository = SimpleNamespace(
        status=lambda *_: {"status": "ready", "result_path": "old.json", "source_sha256": "sha"},
        asset=lambda *_: {"kind": "pdf"},
    )
    reading = ReadingService(repository, tmp_path, parser=None, recover=False)
    monkeypatch.setattr(reading, "_read_source", lambda _: stream.getvalue())
    try:
        content = reading.content("p", "a")
        assert "Ppar" in content.blocks[0].text
        assert content.warnings
        assert path.read_bytes() == before
    finally:
        reading.close()
