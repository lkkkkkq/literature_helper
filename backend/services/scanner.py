"""Read-only discovery. No parsing, OCR or old application state is used."""

import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from backend.core.errors import DomainError
from backend.core.schemas import AssetSnapshot, GroupSuggestion, ScanSnapshot

SUPPORTED = {
    ".pdf",
    ".csv",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".txt",
    ".zip",
}
SUPPLEMENT = re.compile(
    r"(?:^|[\W_])(supp(?:lement(?:ary|al)?)?|supporting|si|esm|s\d+)(?:$|[\W_])"
    r"|补充|附件",
    re.I,
)


def source_folder(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DomainError("请选择绝对路径的文献文件夹。")
    try:
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise DomainError("所选路径不是文件夹。")
        return path
    except OSError as error:
        raise DomainError("源文件夹不存在或无法访问，请检查路径与权限。") from error


def supplemental(path: str) -> bool:
    p = PurePosixPath(path)
    return bool(SUPPLEMENT.search(p.stem) or any(SUPPLEMENT.search(x) for x in p.parts[:-1]))


def normalized(stem: str) -> str:
    return re.sub(r"[\W_]+", "", stem.casefold())


def suggest_groups(assets: list[AssetSnapshot]) -> list[GroupSuggestion]:
    paths = sorted(asset.relative_path for asset in assets)
    mains = [p for p in paths if PurePosixPath(p).suffix.lower() == ".pdf" and not supplemental(p)]
    for path in paths:
        if PurePosixPath(path).suffix.lower() == ".docx" and not supplemental(path):
            if not any(PurePosixPath(p).parent == PurePosixPath(path).parent for p in mains):
                mains.append(path)
    groups = {
        p: GroupSuggestion(
            key=p,
            title=PurePosixPath(p).stem,
            main_path=p,
            asset_paths=[p],
            confidence="high",
            reason="独立主论文候选",
        )
        for p in mains
    }
    unassigned: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        if path in groups:
            continue
        parent = PurePosixPath(path).parent
        candidates = []
        for ancestor in [parent, *parent.parents]:
            candidates = [p for p in mains if PurePosixPath(p).parent == ancestor]
            if candidates:
                break
        matches = [
            p
            for p in candidates
            if normalized(PurePosixPath(path).stem).startswith(normalized(PurePosixPath(p).stem))
        ]
        chosen = (
            matches[0] if len(matches) == 1 else candidates[0] if len(candidates) == 1 else None
        )
        if chosen:
            groups[chosen].asset_paths.append(path)
            groups[chosen].reason = "文件名匹配或所属子目录只有一篇主论文"
        else:
            unassigned[str(parent)].append(path)
    # Several PDFs in one paper subfolder may contain an unlabeled supplement.
    for path, group in groups.items():
        parent = PurePosixPath(path).parent
        if str(parent) != "." and sum(PurePosixPath(p).parent == parent for p in mains) > 1:
            group.confidence = "review"
            group.reason = "同一子目录有多篇主论文候选，请检查是否为未标注的补充材料"
    result = list(groups.values())
    for parent, members in unassigned.items():
        result.append(
            GroupSuggestion(
                key=f"orphan:{parent}",
                title=f"待归属附件 · {parent}",
                main_path=None,
                asset_paths=members,
                confidence="review",
                reason="没有唯一的主论文匹配；可保留为独立资料或合并到其他文献",
            )
        )
    return sorted(result, key=lambda group: group.key.casefold())


def scan_folder(root: Path) -> ScanSnapshot:
    assets = []
    warnings = []

    def on_error(error):
        raise DomainError(f"无法完整扫描文件夹：{error.filename}。已有索引未修改。") from error

    for folder, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        retained = []
        for name in sorted(dirs):
            child = Path(folder) / name
            if name.startswith(".") or name in {"node_modules", "__pycache__"}:
                continue
            if child.is_symlink() or child.is_junction():
                warnings.append(f"已跳过链接目录：{child.relative_to(root)}")
            else:
                retained.append(name)
        dirs[:] = retained
        for name in sorted(files):
            if name.startswith((".", "~$")):
                continue
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                warnings.append(f"已跳过链接文件：{relative}")
                continue
            if path.suffix.lower() not in SUPPORTED:
                warnings.append(f"暂不支持，已跳过：{relative}")
                continue
            try:
                if not path.resolve().is_relative_to(root):
                    raise DomainError(f"文件越过源目录边界：{relative}")
                before = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ino,
                ):
                    raise DomainError(f"扫描期间文件发生变化，请重试：{relative}", "conflict")
                assets.append(
                    AssetSnapshot(
                        relative_path=relative,
                        absolute_path=str(path.resolve()),
                        size=after.st_size,
                        mtime_ns=after.st_mtime_ns,
                        sha256=digest.hexdigest(),
                        kind=path.suffix.lower().lstrip("."),
                    )
                )
            except OSError as error:
                raise DomainError(f"无法读取文件：{relative}。已有索引未修改。") from error
    return ScanSnapshot(assets=assets, groups=suggest_groups(assets), warnings=warnings)
