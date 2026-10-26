"""Replace selected PDF pages in a new immutable full version."""

import shutil

from backend.core.errors import DomainError
from backend.parsing_next.bundle import Bundle, load_bundle, safe_child


def merge_pages(previous, replacement, destination, source, version):
    old_text, old_index, old_report = load_bundle(previous)
    new_text, new_index, new_report = load_bundle(replacement)
    if old_index["source_sha256"] != new_index["source_sha256"]:
        raise DomainError("源文件版本不同，不能只替换部分页面。")
    replaced = set(new_report["pages"] or [])
    if not replaced or not old_report.get("full_document"):
        raise DomainError("逐页重做需要此前完整 PDF 解析版本。")
    bundle = Bundle(destination, source, version)
    selected = []
    for root, text, index, retain in [
        (previous, old_text, old_index, False),
        (replacement, new_text, new_index, True),
    ]:
        for order, block in enumerate(index["blocks"]):
            pages = {loc["page"] for loc in block["locations"] if loc.get("page")}
            if bool(pages & replaced) != retain:
                continue
            if pages & replaced and pages - replaced:
                raise DomainError("此块跨越修复范围，请将关联页面一起重做。")
            selected.append((min(pages, default=0), order, root, text, block))
    for _, _, root, text, block in sorted(selected, key=lambda item: (item[0], item[1])):
        for name in block["resources"]:
            target = safe_child(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_child(root, name), target)
        content = text[block["start"] : block["end"]].split("\n", 1)[1]
        bundle.add(
            content,
            kind=block["kind"],
            locations=block["locations"],
            resources=block["resources"],
            replaced_from=block["id"],
        )
    bundle.issues = [issue for issue in old_report["issues"] if issue.get("page") not in replaced]
    bundle.issues.extend(new_report["issues"])
    return bundle.finish(
        engine=new_report["engine"],
        source_sha256=old_index["source_sha256"],
        pages=old_report["pages"],
        total_pages=old_report["total_pages"],
        full_document=True,
        repaired_pages=sorted(replaced),
        previous_version=old_index["version"],
    )
