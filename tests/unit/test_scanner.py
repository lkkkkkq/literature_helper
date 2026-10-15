from pathlib import Path

import pytest

from backend.core.errors import DomainError
from backend.services.scanner import scan_folder, source_folder, supplemental


def put(root, relative):
    file = root / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"fixture")
    return file


def test_grouping_uses_folder_filename_and_marks_ambiguity(tmp_path):
    for name in [
        "a.pdf",
        "a_supp.csv",
        "b.pdf",
        "unknown.csv",
        "study/main.pdf",
        "study/supplementary/table.xlsx",
        "many/one.pdf",
        "many/two.pdf",
        "many/data.csv",
        "office/paper.docx",
        "office/data.csv",
    ]:
        put(tmp_path, name)
    result = scan_folder(tmp_path)
    groups = {group.main_path: group for group in result.groups if group.main_path}
    assert "a_supp.csv" in groups["a.pdf"].asset_paths
    assert "study/supplementary/table.xlsx" in groups["study/main.pdf"].asset_paths
    assert groups["many/one.pdf"].confidence == "review"
    assert "office/data.csv" in groups["office/paper.docx"].asset_paths
    assert any(
        group.main_path is None and "unknown.csv" in group.asset_paths for group in result.groups
    )
    assert len([path for group in result.groups for path in group.asset_paths]) == len(
        result.assets
    )


@pytest.mark.parametrize(
    "name",
    [
        "paper_supp.pdf",
        "Supplementary Material.pdf",
        "paper-ESM.pdf",
        "附件.pdf",
        "supporting/data.pdf",
        "paper_S1.pdf",
    ],
)
def test_supplement_markers(name):
    assert supplemental(name)


def test_hidden_and_unsupported_files_are_not_silently_imported(tmp_path):
    for name in [
        "visible.pdf",
        ".hidden.pdf",
        ".private/paper.pdf",
        "~$temporary.docx",
        "readme.exe",
    ]:
        put(tmp_path, name)
    result = scan_folder(tmp_path)
    assert [asset.relative_path for asset in result.assets] == ["visible.pdf"]
    assert any("readme.exe" in warning for warning in result.warnings)


def test_linked_files_are_skipped(tmp_path, monkeypatch):
    linked = put(tmp_path, "external.pdf")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == linked or original(self))
    result = scan_folder(tmp_path)
    assert not result.assets
    assert result.warnings


def test_rejects_file_as_source(tmp_path):
    file = put(tmp_path, "paper.pdf")
    with pytest.raises(DomainError):
        source_folder(str(file))


def test_empty_folder_has_valid_empty_snapshot(tmp_path):
    result = scan_folder(tmp_path)
    assert not result.assets
    assert not result.groups
