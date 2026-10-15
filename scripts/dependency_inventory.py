"""Generate dependency locks and provenance from installed package metadata."""

import importlib.metadata as metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clean(value):
    return str(value).replace("|", "/").replace("\n", " ").strip()


def generate():
    packages = sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower())
    locked = [
        f"{item.metadata['Name']}=={item.version}"
        for item in packages
        if item.metadata["Name"].lower() not in {"litextract-v2", "pip"}
    ]
    (ROOT / "requirements.lock").write_text(
        "# Generated from the verified Python environment; install with pip -r.\n"
        + "\n".join(locked)
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Third-party notices",
        "",
        "Generated from installed package metadata and package-lock.json. "
        "Direct integration only; no upstream source copied or modified.",
        "Model weight provenance and usage are recorded separately in MODEL_NOTICES.md.",
        "",
        "Exact npm integrity hashes are in package-lock.json. "
        "Python pins are in requirements.lock. "
        "License texts remain in each installed distribution. Before shipping an installer, "
        "bundle those texts and Electron's LICENSE / LICENSES.chromium.html.",
        "",
        "Python license metadata may use a full notice rather than an SPDX identifier; "
        "only its first line is shown below. Review the original license files for distribution.",
        "",
        "## Python dependencies",
        "",
        "| Library | Version | License metadata | Upstream | Use / modifications |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in packages:
        info = item.metadata
        if info["Name"].lower() in {"litextract-v2", "pip"}:
            continue
        license_name = info.get("License-Expression") or info.get("License")
        if not license_name:
            license_name = (
                "; ".join(
                    value.split(" :: ")[-1]
                    for value in info.get_all("Classifier", [])
                    if value.startswith("License ::")
                )
                or "See installed LICENSE"
            )
        urls = info.get_all("Project-URL", [])
        url = next(
            (
                value.split(", ", 1)[-1]
                for value in urls
                if value.split(",", 1)[0].lower() in {"source", "repository"}
            ),
            info.get("Home-page") or (urls[0].split(", ", 1)[-1] if urls else ""),
        )
        if info["Name"].lower() == "pluggy":
            url = "https://github.com/pytest-dev/pluggy"
        lines.append(
            f"| {clean(info['Name'])} | {item.version} | {clean(license_name.splitlines()[0])} "
            f"| {clean(url)} | Package integration; unmodified |"
        )
    lines += [
        "",
        "## JavaScript dependencies (including transitive packages)",
        "",
        "| Library | Version | License metadata | Upstream | Use / modifications |",
        "| --- | --- | --- | --- | --- |",
    ]
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for location, entry in sorted(lock["packages"].items()):
        if not location:
            continue
        package_file = ROOT / location / "package.json"
        info = json.loads(package_file.read_text(encoding="utf-8")) if package_file.exists() else {}
        name = info.get("name", location.split("node_modules/")[-1])
        repository = info.get("repository", {})
        url = repository.get("url", "") if isinstance(repository, dict) else repository
        url = url or f"https://www.npmjs.com/package/{name}"
        license_name = entry.get("license", info.get("license", "See package LICENSE"))
        lines.append(
            f"| {clean(name)} | {entry['version']} | {clean(license_name)} | {clean(url)} "
            "| Package integration; unmodified |"
        )
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
