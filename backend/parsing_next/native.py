"""Read native cells and document structures without executing document code."""

import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from backend.core.errors import DomainError
from backend.parsing_next.bundle import Bundle, safe_child, write_json


def table_html(rows):
    return (
        "<table>\n"
        + "\n".join(
            "<tr>"
            + "".join(f"<td>{html.escape(str(v if v is not None else ''))}</td>" for v in row)
            + "</tr>"
            for row in rows
        )
        + "\n</table>"
    )


def read_tabular(source: Path, bundle: Bundle):
    if source.suffix.lower() == ".csv":
        data = source.read_bytes()
        try:
            text = data.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            from charset_normalizer import from_bytes

            detected = from_bytes(data).best()
            if detected is None:
                raise DomainError("无法确定 CSV 编码，请另存为 UTF-8 后重试。") from None
            text, encoding = str(detected), detected.encoding
            bundle.issues.append(
                {
                    "kind": "encoding_inferred",
                    "encoding": encoding,
                    "message": "非 UTF-8 文件，编码为推断值；请核对单位和特殊符号。",
                }
            )
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(text.splitlines(keepends=True), dialect))
        shutil.copy2(source, bundle.root / "attachments" / source.name)
        bundle.add(
            table_html(rows),
            kind="table",
            locations=[{"file": source.name, "rows": [1, len(rows)]}],
            resources=[f"attachments/{source.name}"],
            encoding=encoding,
            data_origin="original_data",
        )
        return
    import openpyxl

    formulas = openpyxl.load_workbook(source, data_only=False)
    values = openpyxl.load_workbook(source, data_only=True)
    try:
        for number, sheet in enumerate(formulas.worksheets):
            cells, rows = [], []
            for row in sheet:
                rendered = []
                for cell in row:
                    value = cell.value
                    record = {
                        "cell": cell.coordinate,
                        "value": value,
                        "number_format": cell.number_format,
                    }
                    if cell.data_type == "f":
                        cached = values[sheet.title][cell.coordinate].value
                        record = {
                            "cell": cell.coordinate,
                            "formula": value,
                            "cached_value": cached,
                            "number_format": cell.number_format,
                        }
                        value = f"{value} [cached: {cached if cached is not None else 'missing'}]"
                        if cached is None:
                            bundle.issues.append(
                                {
                                    "kind": "formula_cache_missing",
                                    "sheet": sheet.title,
                                    "cell": cell.coordinate,
                                }
                            )
                    if cell.value is not None:
                        cells.append(record)
                    rendered.append(value)
                rows.append(rendered)
            resource = f"attachments/sheet-{number + 1}.json"
            write_json(
                bundle.root / resource,
                {
                    "sheet": sheet.title,
                    "cells": cells,
                    "merged_ranges": [str(r) for r in sheet.merged_cells.ranges],
                    "data_origin": "original_data",
                },
            )
            bundle.add(
                f"## {sheet.title}\n\n" + table_html(rows),
                kind="table",
                locations=[
                    {
                        "file": source.name,
                        "sheet": sheet.title,
                        "range": sheet.calculate_dimension(),
                    }
                ],
                resources=[resource],
            )
    finally:
        formulas.close()
        values.close()


def pandoc_path():
    configured = os.environ.get("LITEXTRACT_PANDOC")
    if configured:
        return configured
    bundled = (
        Path(__file__).resolve().parents[2]
        / ".local/parser-next/venv/Lib/site-packages/pypandoc/files/pandoc.exe"
    )
    found = shutil.which("pandoc") or (str(bundled) if bundled.is_file() else None)
    if not found:
        raise DomainError("Pandoc 尚未准备，请配置 LITEXTRACT_PANDOC。")
    return found


def stage_text(source: Path, target: Path, issues, visited=None, dependencies=None):
    """Resolve local LaTeX dependencies only; never run TeX or shell escapes."""
    visited = visited if visited is not None else set()
    root = source.parent.resolve()

    def copy(path, destination):
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():
            issues.append({"kind": "unsafe_dependency", "file": path.name})
            return
        if resolved in visited:
            return
        visited.add(resolved)
        if not path.is_file():
            issues.append({"kind": "missing_dependency", "file": path.name})
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        if dependencies is not None:
            dependencies.append(
                {
                    "file": resolved.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        if path.suffix.lower() not in {".tex", ".md", ".bib"}:
            destination.write_bytes(raw)
            return
        text = raw.decode("utf-8-sig")
        # Do not let Pandoc resolve undeclared absolute or escaping source dependencies.
        dependency_pattern = (
            r"\\(input|include|includegraphics|bibliography|addbibresource)"
            r"(?:\[[^]]*\])?\{([^}]+)\}"
        )

        def reject_escaping(match):
            names = match.group(2).split(",")
            if any(
                re.match(r"^[a-zA-Z]+:", name)
                or not (path.parent / name).resolve().is_relative_to(root)
                for name in names
            ):
                issues.append({"kind": "unsafe_dependency", "file": match.group(2)})
                return "[外部依赖未读取]"
            return match.group(0)

        text = re.sub(dependency_pattern, reject_escaping, text)
        if re.search(r"\\(?:write18|immediate|openout|read|catcode)\b", text):
            issues.append({"kind": "tex_code_not_executed", "file": path.name})
        for command, name in re.findall(
            r"\\(input|include|includegraphics|bibliography|addbibresource)(?:\[[^]]*\])?\{([^}]+)\}",
            text,
        ):
            for dependency in name.split(","):
                child = path.parent / dependency
                if not child.suffix:
                    suffixes = (
                        [".tex"]
                        if command in {"input", "include"}
                        else (
                            [".bib"]
                            if command in {"bibliography", "addbibresource"}
                            else [".png", ".jpg", ".pdf", ".svg"]
                        )
                    )
                    child = next(
                        (child.with_suffix(s) for s in suffixes if child.with_suffix(s).is_file()),
                        child.with_suffix(suffixes[0]),
                    )
                if child.resolve().is_relative_to(root):
                    copy(child, target / child.resolve().relative_to(root))
                else:
                    issues.append({"kind": "unsafe_dependency", "file": dependency})
        destination.write_text(text, encoding="utf-8")

    copy(source, target / source.name)


def run_native(command, *, cancel=None, timeout=120, input=None, cwd=None):
    started = time.monotonic()
    with subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        try:
            while True:
                if cancel and cancel.is_set():
                    raise DomainError("原生文档解析已取消。")
                if time.monotonic() - started > timeout:
                    raise DomainError("原生文档转换超时；未自动重试。")
                try:
                    stdout, stderr = process.communicate(input=input, timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    input = None
            if process.returncode:
                raise DomainError(
                    "Pandoc 未能完成转换：" + stderr.decode("utf-8", errors="replace")[-1000:]
                )
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def read_document(source: Path, bundle: Bundle, cancel=None):
    staging = bundle.root / "attachments" / "source"
    staging.mkdir()
    if source.suffix.lower() in {".tex", ".md"}:
        stage_text(source, staging, bundle.issues, dependencies=bundle.dependencies)
    else:
        shutil.copy2(source, staging / source.name)
    executable = pandoc_path()
    # First parse to AST without fetching resources. Images are explicitly copied below.
    result = run_native(
        [executable, str(staging / source.name), "-t", "json"],
        cwd=staging,
        cancel=cancel,
        timeout=120,
    )
    ast = json.loads(result.stdout)
    image_map = {}
    if source.suffix.lower() == ".docx":
        with ZipFile(source) as archive:
            for name in archive.namelist():
                if name.startswith("word/media/") and not name.endswith("/"):
                    raw = archive.read(name)
                    image_name = hashlib.sha256(raw).hexdigest()[:20] + Path(name).suffix.lower()
                    resource = f"images/{image_name}"
                    (bundle.root / resource).write_bytes(raw)
                    image_map[name.removeprefix("word/")] = resource
            extract_docx_charts(archive, bundle)

    def walk(node, resources):
        if isinstance(node, list):
            for item in node:
                walk(item, resources)
        elif isinstance(node, dict):
            if node.get("t") == "Image":
                name = node["c"][-1][0]
                resource = image_map.get(name)
                if not resource and not re.match(r"^[a-zA-Z]+:", name):
                    local = source.parent / name
                    if local.is_file() and local.resolve().is_relative_to(source.parent.resolve()):
                        raw = local.read_bytes()
                        bundle.dependencies.append(
                            {
                                "file": local.relative_to(source.parent).as_posix(),
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            }
                        )
                        resource = "images/" + hashlib.sha256(raw).hexdigest()[:20] + local.suffix
                        safe_child(bundle.root, resource).write_bytes(raw)
                if resource:
                    resources.append(resource)
                    node["c"][-1][0] = resource
                else:
                    bundle.issues.append({"kind": "missing_resource", "resource": name})
                    node["c"][-1][0] = "missing-resource"
            for value in node.values():
                walk(value, resources)

    annotated, resources_by_block = [], []
    original_blocks = ast["blocks"]
    for index, block in enumerate(original_blocks):
        resources = []
        walk(block, resources)
        resources_by_block.append(resources)
        annotated.extend(
            [{"t": "RawBlock", "c": ["html", f"<!-- native-block:{index} -->"]}, block]
        )
    ast["blocks"] = annotated
    result = run_native(
        [
            executable,
            "-f",
            "json",
            "-t",
            "markdown+raw_html+tex_math_dollars-grid_tables-multiline_tables-simple_tables",
            "--wrap=none",
        ],
        input=json.dumps(ast).encode(),
        cancel=cancel,
        timeout=120,
    )
    parts = re.split(r"<!-- native-block:\d+ -->", result.stdout.decode("utf-8"))[1:]
    if len(parts) != len(original_blocks):
        raise DomainError("原生文档块数不一致，未激活不完整结果。")
    for index, (text, block, resources) in enumerate(
        zip(parts, original_blocks, resources_by_block, strict=True)
    ):
        kind = "table" if block["t"] == "Table" else "picture" if resources else "text"
        bundle.add(
            text,
            kind=kind,
            resources=resources,
            locations=[{"file": source.name, "native_block": index + 1}],
            native_type=block["t"],
        )
    if result.stderr:
        bundle.issues.append(
            {
                "kind": "conversion_warning",
                "message": result.stderr.decode("utf-8", errors="replace"),
            }
        )


def extract_docx_charts(archive, bundle):
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    for name in archive.namelist():
        if not re.fullmatch(r"word/charts/chart\d+\.xml", name):
            continue
        tree = ET.fromstring(archive.read(name))
        series = []
        for item in tree.findall(".//c:ser", ns):
            values = {}
            for role in ("tx", "cat", "val", "xVal", "yVal"):
                values[role] = [node.text for node in item.findall(f"c:{role}//c:v", ns)]
            series.append(values)
        resource = f"chart-data/{Path(name).stem}-native.json"
        write_json(
            bundle.root / resource,
            {
                "data_origin": "native_chart_cache",
                "source": name,
                "series": series,
                "reviewed": False,
            },
        )
        bundle.add(
            f"原生图表缓存数据：{Path(name).stem}",
            kind="chart",
            locations=[{"file": bundle.source.name, "package_part": name}],
            resources=[resource],
        )


def parse_native(source, output, version=None, cancel=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    bundle = Bundle(output, source, version)
    if source.suffix.lower() in {".csv", ".xlsx"}:
        read_tabular(source, bundle)
        engine = "python-csv/openpyxl"
    elif source.suffix.lower() in {".docx", ".tex", ".md"}:
        read_document(source, bundle, cancel)
        engine = "pandoc"
    else:
        raise DomainError("此原生格式尚未支持。")
    for dependency in bundle.dependencies:
        path = safe_child(source.parent, dependency["file"])
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != dependency["sha256"]
        ):
            raise DomainError("解析期间依赖文件发生变化，请重新解析。")
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise DomainError("解析期间源文件发生变化，请重新解析。")
    return bundle.finish(engine=engine, source_sha256=source_hash)
