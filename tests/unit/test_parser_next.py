import hashlib
import json
import threading
import time
from types import SimpleNamespace

import openpyxl
import pytest

from backend.core.errors import DomainError
from backend.parsing_next.bundle import Bundle, fulltext_batches, load_bundle, safe_child
from backend.parsing_next.charts import ChartInput, digitize
from backend.parsing_next.native import parse_native
from backend.parsing_next.service import FullDocumentService


def chart(**changes):
    return ChartInput.model_validate(
        {
            "resource": "images/figure.png",
            "panel": "A",
            "series": "blue",
            "kind": "scatter",
            "calibrated": True,
            "origin": {"x": 0.1, "y": 0.9},
            "x_reference": {"x": 0.9, "y": 0.9},
            "y_reference": {"x": 0.1, "y": 0.1},
            "x_min": 10,
            "x_max": 30,
            "y_min": 0,
            "y_max": 100,
            "points": [{"x": 0.5, "y": 0.5}],
            **changes,
        }
    )


def test_chart_calibration_linear_log_bar_and_singular_axes():
    assert digitize(chart())[0]["x"] == pytest.approx(20)
    assert digitize(chart())[0]["y"] == pytest.approx(50)
    assert digitize(chart(x_min=1, x_max=100, x_log=True))[0]["x"] == pytest.approx(10)
    row = digitize(chart(kind="bar", points=[{"x": 0.5, "y": 0.3, "category": "PET"}]))[0]
    assert row["value"] == pytest.approx(75)
    assert row["category"] == "PET"
    with pytest.raises(DomainError, match="共线"):
        digitize(chart(y_reference={"x": 0.9, "y": 0.9}))
    with pytest.raises(ValueError):
        chart(x_log=True, x_min=0)


def test_heatmap_and_pie_distinguish_estimates_and_labels():
    heat = chart(
        kind="heatmap",
        points=[{"x": 0.5, "y": 0.5, "rgb": [128, 0, 128]}],
        color_scale=[
            {"x": 0, "y": 0, "rgb": [0, 0, 255], "label_value": 0},
            {"x": 1, "y": 1, "rgb": [255, 0, 0], "label_value": 100},
        ],
    )
    assert digitize(heat)[0]["value"] == pytest.approx(50)
    pie = chart(
        kind="pie",
        origin={"x": 0.5, "y": 0.5},
        points=[{"x": 1, "y": 0.5}, {"x": 0.5, "y": 1}, {"x": 0, "y": 0.5}, {"x": 0.5, "y": 0}],
    )
    assert [row["value"] for row in digitize(pie)] == pytest.approx([25] * 4)
    labeled = chart(kind="manual", points=[{"x": 0.5, "y": 0.5, "label_value": 12.5}])
    assert digitize(labeled)[0]["data_origin"] == "chart_label"


def test_bundle_versions_fulltext_coverage_and_tamper(tmp_path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"original")
    root = tmp_path / "bundle"
    bundle = Bundle(root, source)
    first = bundle.add("α" * 700, locations=[{"page": 1}])
    bundle.add("tail\r\nWindows line endings\r\n", locations=[{"page": 2}])
    bundle.finish(engine="fixture", source_sha256="sha", pages=[1, 2])
    result = fulltext_batches(root, 256)
    assert result["complete"] and len(result["batches"]) >= 3
    assert first.startswith(bundle.version)
    assert "α" not in (root / "sources.json").read_text("utf-8")
    assert "".join(row["text"] for row in result["batches"]) == (root / "paper.md").read_text(
        "utf-8"
    )
    with pytest.raises(DomainError):
        safe_child(root, "../outside")
    (root / "paper.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(DomainError, match="摘要"):
        load_bundle(root)


def test_native_cells_preserve_formula_cache_and_merged_header(tmp_path):
    source = tmp_path / "values.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "Abundance (particles/m³)"
    sheet.merge_cells("A1:B1")
    sheet["A2"] = 0.00004
    sheet["B2"] = "=A2*1000"
    workbook.save(source)
    before = source.read_bytes()
    report = parse_native(source, tmp_path / "parsed")
    cells = json.loads((tmp_path / "parsed/attachments/sheet-1.json").read_text("utf-8"))
    assert cells["merged_ranges"] == ["A1:B1"]
    assert cells["cells"][-1]["formula"] == "=A2*1000"
    assert cells["cells"][-1]["cached_value"] is None
    assert report["issues"][0]["kind"] == "formula_cache_missing"
    assert source.read_bytes() == before


def test_failed_reparse_keeps_active_and_corrections_are_append_only(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("unit,value\nmg/L,12.5\n", encoding="utf-8")
    asset = {
        "id": "a",
        "kind": "csv",
        "absolute_path": str(source),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    reading = SimpleNamespace(
        repository=SimpleNamespace(asset=lambda *_: asset),
        _read_source=lambda _: source.read_bytes(),
    )
    service = FullDocumentService(reading, tmp_path / "data")

    def wait():
        for _ in range(100):
            state = service.status("p", "a")
            if state["status"] not in {"queued", "running"}:
                return state
            time.sleep(0.02)
        pytest.fail("parser did not finish")

    try:
        service.start("p", "a")
        state = wait()
        assert state["status"] == "ready"
        version = state["active"]["version"]
        content = service.content("p", "a", version)
        block_id = content["blocks"][0]["id"]
        before = (service.version_folder("p", "a", version) / "paper.md").read_bytes()
        service.correct(
            "p",
            "a",
            version,
            {"block_id": block_id, "markdown": "reviewed", "reason": "checked", "base_revision": 0},
        )
        with pytest.raises(DomainError, match="已变化"):
            service.correct(
                "p",
                "a",
                version,
                {
                    "block_id": block_id,
                    "markdown": "stale",
                    "reason": "checked",
                    "base_revision": 0,
                },
            )
        assert (service.version_folder("p", "a", version) / "paper.md").read_bytes() == before
        monkeypatch.setattr(
            "backend.parsing_next.service.parse_native",
            lambda *args: (_ for _ in ()).throw(ValueError("fixture failed")),
        )
        service.start("p", "a")
        state = wait()
        assert state["status"] == "failed"
        assert state["active"]["version"] == version
    finally:
        service.close()


def test_cancelled_process_does_not_leave_child_running(tmp_path):
    from backend.parsing_next.runner import run_parser

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(DomainError, match="取消|环境"):
        run_parser(tmp_path / "missing.pdf", tmp_path / "result", cancel=cancelled)


def test_page_repair_preserves_other_pages_and_old_version(tmp_path):
    from backend.parsing_next.repair import merge_pages

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"fixture")
    old = Bundle(tmp_path / "old", source)
    old.add("first page", locations=[{"page": 1}])
    old.add("bad second page", locations=[{"page": 2}])
    old.finish(
        engine="fixture", source_sha256="sha", pages=[1, 2], total_pages=2, full_document=True
    )
    before = (tmp_path / "old/paper.md").read_bytes()
    replacement = Bundle(tmp_path / "replacement", source)
    replacement.add("corrected second page", locations=[{"page": 2}])
    replacement.finish(
        engine="fixture", source_sha256="sha", pages=[2], total_pages=2, full_document=False
    )
    merge_pages(tmp_path / "old", tmp_path / "replacement", tmp_path / "new", source, "new")
    text, index, report = load_bundle(tmp_path / "new")
    assert "first page" in text and "corrected second page" in text
    assert "bad second page" not in text
    assert report["pages"] == [1, 2] and report["repaired_pages"] == [2]
    assert (tmp_path / "old/paper.md").read_bytes() == before
    assert all(block["id"].startswith("new:") for block in index["blocks"])


def test_dependency_changes_block_fulltext_and_chart_export_covers_rows(tmp_path):
    from backend.parsing_next.bundle import write_json
    from backend.parsing_next.context import active_sources

    source = tmp_path / "main.md"
    source.write_text("source")
    dependency = tmp_path / "section.tex"
    dependency.write_text("original")
    root = tmp_path / "data/parser-next/p/a"
    bundle = Bundle(root / "v", source, "v")
    bundle.dependencies.append(
        {"file": "section.tex", "sha256": hashlib.sha256(dependency.read_bytes()).hexdigest()}
    )
    (bundle.root / "images/chart.png").write_bytes(b"fixture")
    bundle.add("chart", resources=["images/chart.png"])
    bundle.finish(engine="test", source_sha256="sha")
    write_json(root / "active.json", {"version": "v", "source_sha256": "sha"})
    write_json(
        bundle.root / "chart-data/revision-000001.json",
        {
            "specification": {
                "resource": "images/chart.png",
                "panel": "A",
                "series": "B",
                "confirmed": True,
                "kind": "scatter",
                "x_unit": "s",
                "y_unit": "m",
            },
            "rows": [{"x": 1, "y": 2}],
        },
    )
    assert '"y": 2' in fulltext_batches(bundle.root, 1000)["batches"][0]["text"]
    reading = SimpleNamespace(
        data_dir=tmp_path / "data",
        repository=SimpleNamespace(asset=lambda *_: {"absolute_path": str(source)}),
        _read_source=lambda _: source.read_bytes(),
    )
    asset = {"id": "a", "sha256": "sha", "relative_path": source.name}
    assert len(active_sources(reading, "p", "d", asset)[0]) == 2
    dependency.write_text("changed")
    with pytest.raises(DomainError, match="依赖文件已变化"):
        active_sources(reading, "p", "d", asset)


def test_rotation_boxes_map_back_to_original_view():
    from backend.parsing_next.mineru_worker import rotated_box

    assert rotated_box([0.1, 0.2, 0.3, 0.4], 90) == pytest.approx([0.6, 0.1, 0.8, 0.3])
    assert rotated_box([0.1, 0.2, 0.3, 0.4], 180) == pytest.approx([0.7, 0.6, 0.9, 0.8])


def test_native_conversion_cancel_and_timeout():
    import sys

    from backend.parsing_next.native import run_native

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DomainError, match="取消"):
        run_native([sys.executable, "-c", "import time; time.sleep(60)"], cancel=cancel)
    with pytest.raises(DomainError, match="超时"):
        run_native([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.1)
