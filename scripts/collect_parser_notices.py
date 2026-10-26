"""Archive public attribution and matching unmodified Pandoc sources, never papers."""

import hashlib
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PANDOC_SHA = "85e685ee8c8407ea40844145df3cbc1e8469e861dc3454f86dbfd23122aa27e6"


def main():
    target = ROOT / ".local/parser-next/license-evidence"
    target.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    def save(url, name):
        response = session.get(url, timeout=(30, 180))
        response.raise_for_status()
        (target / name).write_bytes(response.content)
        return response.content

    base = "https://huggingface.co/"
    repo = "opendatalab/MinerU-4_models_onnx"
    manifest = json.loads(
        save(base + repo + "/resolve/main/manifest.json", "MinerU-4_models_onnx-manifest.json")
    )
    repositories = {item["source"]["repo"] for item in manifest["files"]}
    repositories.update(
        {repo, "opendatalab/MinerU2.5-Pro-2605-1.2B", "jinzhenj/MinerU2.5-Pro-2605-1.2B-GGUF"}
    )
    for repository in sorted(repositories):
        save(base + "api/models/" + repository, repository.replace("/", "--") + "-metadata.json")
    for repository in [repo, "opendatalab/MinerU2.5-Pro-2605-1.2B"]:
        save(
            base + repository + "/resolve/main/README.md", repository.split("/")[-1] + "-README.md"
        )
    archive = save(
        "https://codeload.github.com/jgm/pandoc/tar.gz/refs/tags/3.6.1",
        "pandoc-3.6.1-source.tar.gz",
    )
    if hashlib.sha256(archive).hexdigest() != PANDOC_SHA:
        raise RuntimeError("Pandoc source archive differs from tested release")
    print("Public parser notices archived; review MODEL_NOTICES.md for license distinctions")


if __name__ == "__main__":
    main()
