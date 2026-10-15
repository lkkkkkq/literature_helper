"""Download only the models used by the local CPU PDF pipeline."""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def download_ocr(output: Path):
    from easyocr.config import detection_models, recognition_models

    folder = output / "EasyOcr"
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2)))
    models = [detection_models["craft"], recognition_models["gen2"]["zh_sim_g2"]]
    for model in models:
        target = folder / model["filename"]
        if target.exists() and hashlib.md5(target.read_bytes()).hexdigest() == model["md5sum"]:
            continue
        print(f"Downloading OCR model: {model['filename']}", flush=True)
        response = session.get(model["url"], timeout=(60, 120))
        response.raise_for_status()
        with ZipFile(BytesIO(response.content)) as archive:
            data = archive.read(model["filename"])
        if hashlib.md5(data).hexdigest() != model["md5sum"]:
            raise ValueError(f"Model checksum mismatch: {model['filename']}")
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)


def main():
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".local/docling-models"))
    args = parser.parse_args()
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "models.lock.json").read_text(encoding="utf-8")
    )
    for repository, revision in manifest["revisions"].items():
        snapshot_download(
            repo_id=repository,
            revision=revision,
            local_dir=args.output.resolve() / repository.replace("/", "--"),
        )
    download_ocr(args.output.resolve())
    for relative, expected in manifest["files"].items():
        if relative.startswith("licenses/"):
            continue  # License texts are bundled by the release script from the source repository.
        if hashlib.sha256((args.output / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Model checksum mismatch: {relative}")
    print(f"PDF models ready: {args.output.resolve()}")


if __name__ == "__main__":
    main()
