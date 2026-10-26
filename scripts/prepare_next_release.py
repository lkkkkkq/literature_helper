"""Vendor the tested separate 3.12 runtime; no user papers, caches, or keys."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copy(source, target):
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".cache", ".locks"),
    )


def main():
    experiment = ROOT / ".local/parser-next"
    if not (experiment / "license-evidence/pandoc-3.6.1-source.tar.gz").is_file():
        raise RuntimeError("Run scripts/collect_parser_notices.py before preparing a release")
    interpreter = experiment / "venv/Scripts/python.exe"
    base = Path(
        subprocess.check_output(
            [str(interpreter), "-c", "import sys; print(sys.base_prefix)"], text=True
        ).strip()
    )
    destination = ROOT / ".local/release/engine-next"
    copy(base, destination)
    copy(ROOT / "backend", destination / "backend")
    copy(experiment / "venv/Lib/site-packages", destination / "Lib/site-packages")
    models = experiment / "mineru-home/models"
    target_models = ROOT / ".local/release/parser-models"
    copy(models, target_models)
    manifest = {}
    for path in sorted(target_models.rglob("*")):
        if path.is_file():
            manifest[path.relative_to(target_models).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    locked = json.loads((ROOT / "parser-next.models.lock.json").read_text("utf-8"))["files"]
    if manifest != locked:
        raise RuntimeError("Parser model hashes differ from the tested lock; release stopped")
    notices = ROOT / ".local/release/notices/parser-next"
    notices.mkdir(parents=True, exist_ok=True)
    copy(experiment / "license-evidence", notices / "model-provenance")
    for name in [
        "parser-next.requirements.lock",
        "parser-next.models.lock.json",
        "PARSER_PROGRESS.md",
        "PARSER_GUIDE.md",
        "MODEL_NOTICES.md",
    ]:
        shutil.copy2(ROOT / name, notices / name)
    for directory in (destination / "Lib/site-packages").glob("*.dist-info"):
        for path in directory.rglob("*"):
            if path.is_file() and any(
                term in path.name.lower() for term in ("license", "notice", "copying")
            ):
                target = notices / directory.name / path.relative_to(directory)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    shutil.copy2(
        destination / "Lib/site-packages/pypandoc/files/COPYRIGHT.txt",
        notices / "PANDOC-COPYRIGHT.txt",
    )
    print("Prepared isolated parser runtime and verified model file hashes")


if __name__ == "__main__":
    main()
