"""Record the reviewed local model bytes and upstream commit IDs for release verification."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / ".local/docling-models"
    revisions = {}
    for folder in directory.iterdir():
        metadata = folder / ".cache/huggingface/download/README.md.metadata"
        if metadata.exists():
            revisions[folder.name.replace("--", "/", 1)] = metadata.read_text().splitlines()[0]
    files = {
        file.relative_to(directory).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(directory.rglob("*"))
        if file.is_file() and ".cache" not in file.parts
    }
    (ROOT / "models.lock.json").write_text(
        json.dumps({"revisions": revisions, "files": files}, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
