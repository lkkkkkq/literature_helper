"""Vendor a relocatable official CPython runtime, dependencies, models and notices."""

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import requests

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.13.16"
URL = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip"
SHA256 = "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"


def copy_tree(source, target):
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".cache", "__editable__*"),
    )


def main():
    stage = ROOT / ".local/release"
    if stage.exists():
        expected_parent = (ROOT / ".local").resolve()
        if (
            stage.is_symlink()
            or stage.resolve().parent != expected_parent
            or not stage.resolve().is_relative_to(ROOT.resolve())
        ):
            raise RuntimeError("Unsafe release staging path")
        shutil.rmtree(stage)
    engine = stage / "engine"
    engine.mkdir(parents=True, exist_ok=True)
    archive = ROOT / ".local" / f"python-{VERSION}.zip"
    if not archive.exists():
        response = requests.get(URL, timeout=(30, 180))
        response.raise_for_status()
        archive.write_bytes(response.content)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("Official Python archive SHA-256 does not match release page")
    with ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (engine / member.filename).resolve().is_relative_to(engine.resolve()):
                raise RuntimeError("Unsafe archive member")
        bundle.extractall(engine)
    (engine / "python313._pth").write_text(
        "python313.zip\n.\nLib/site-packages\nimport site\n", encoding="utf-8"
    )
    print("Copying vendored Python packages", flush=True)
    copy_tree(ROOT / ".venv/Lib/site-packages", engine / "Lib/site-packages")
    copy_tree(ROOT / "backend", engine / "backend")
    models = ROOT / ".local/docling-models"
    manifest = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        if hashlib.sha256((models / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Model checksum mismatch: {relative}")
    print("Copying verified local models", flush=True)
    copy_tree(models, stage / "models")
    notices = stage / "notices"
    notices.mkdir(exist_ok=True)
    copy_tree(ROOT / "licenses", notices / "models")
    for name in [
        "THIRD_PARTY_NOTICES.md",
        "MODEL_NOTICES.md",
        "README.md",
        "BETA_GUIDE.md",
        "VERIFICATION.md",
        "models.lock.json",
        "requirements.lock",
        "package-lock.json",
    ]:
        shutil.copy2(ROOT / name, notices / name)
    for location in json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))[
        "packages"
    ]:
        if not location:
            continue
        package = ROOT / location
        for file in package.glob("*"):
            if file.is_file() and file.name.lower().startswith(
                ("license", "licence", "notice", "copying")
            ):
                destination = notices / "npm" / location.removeprefix("node_modules/") / file.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)
    shutil.copy2(ROOT / "node_modules/electron/dist/LICENSE", notices / "ELECTRON_LICENSE")
    shutil.copy2(
        ROOT / "node_modules/electron/dist/LICENSES.chromium.html",
        notices / "LICENSES.chromium.html",
    )
    (stage / "runtime.json").write_text(
        json.dumps({"python": VERSION, "url": URL, "sha256": SHA256}, indent=2), encoding="utf-8"
    )
    print(f"Release staging ready: {stage}", flush=True)


if __name__ == "__main__":
    main()
