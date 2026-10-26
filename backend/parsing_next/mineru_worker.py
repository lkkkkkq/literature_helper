"""Run in the isolated MinerU environment. No remote parser or API key is accepted."""

import argparse
import hashlib
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

from backend.parsing_next.bundle import Bundle, safe_child


def rotated_box(box, rotation):
    if not box or not rotation:
        return box
    x0, y0, x1, y1 = box
    return {
        90: (1 - y1, x0, 1 - y0, x1),
        180: (1 - x1, 1 - y1, 1 - x0, 1 - y0),
        270: (y0, 1 - x1, y1, 1 - x0),
    }[rotation]


def parse_pdf(source: Path, output: Path, version_id=None, pages="all"):
    import pypdfium2 as pdfium
    from docvortex.export import materialize_middle
    from mineru.config import VlmConfig, config
    from mineru.parser import parse
    from mineru.render import render_markdown
    from mineru.render.contracts import RenderMode

    config.model.small_backend = "onnx"
    if os.environ.get("LITEXTRACT_PARSER_MODELS"):
        config.model.base_dir = os.environ["LITEXTRACT_PARSER_MODELS"]
        config.model.source = "local"

    def parse_local(path, selected):
        return parse(
            path,
            tier="standard",
            page_range=selected,
            vlm_config=VlmConfig(engine="llama-cpp", server_url="", max_concurrency=1),
        )

    # Respect displayed orientation first. Only empty rotated pages get one local fallback.
    result = parse_local(source, pages)
    middle, assets = materialize_middle(result.middle_json)
    assets = dict(assets.items())
    empty = {page.page_idx for page in middle.pages if not page.blocks}
    rotations = {}
    with tempfile.TemporaryDirectory(prefix="litextract-orientation-") as temporary:
        with pdfium.PdfDocument(source) as document:
            for i in range(len(document)):
                page = document[i]
                rotation = page.get_rotation()
                if rotation and i in empty:
                    rotations[i] = rotation
                    page.set_rotation(0)
                page.close()
            normalized = Path(temporary) / "upright.pdf"
            if rotations:
                document.save(normalized)
        if rotations:
            retry = parse_local(normalized, ",".join(str(i + 1) for i in sorted(rotations)))
            retried, extra_assets = materialize_middle(retry.middle_json)
            replacements = {page.page_idx: page for page in retried.pages}
            middle = middle.model_copy(
                update={"pages": [replacements.get(page.page_idx, page) for page in middle.pages]}
            )
            assets.update(extra_assets.items())
    bundle = Bundle(output, source, version_id)
    for i, rotation in rotations.items():
        bundle.issues.append(
            {
                "kind": "rotation_fallback",
                "page": i + 1,
                "rotation": rotation,
                "message": "原方向未识别到内容；方向归正后本地补读一次，请核对定位。",
            }
        )
    for name, raw in assets.items():
        path = safe_child(output, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    with pdfium.PdfDocument(source) as pdf:
        seen = set()
        for page in middle.pages:
            number = page.page_idx + 1
            seen.add(number)
            print(f"Export page {number}/{len(pdf)}", flush=True)
            for block in page.blocks:
                isolated = middle.model_copy(
                    update={"pages": [page.model_copy(update={"blocks": [block]})]}
                )
                text = render_markdown(isolated, mode=RenderMode.FULL)
                box = rotated_box(block.bbox, rotations.get(page.page_idx, 0))
                location = {
                    "page": number,
                    "bbox": [box[0], box[1], box[2] - box[0], box[3] - box[1]] if box else None,
                }
                resources = []
                for name in assets:
                    if name in text:
                        resources.append(name)
                kind = block.type
                if kind in {"equation", "table", "image", "chart"}:
                    resource = f"images/page-{number}-block-{block.index}.png"
                    pdfpage = pdf[page.page_idx]
                    bitmap = pdfpage.render(scale=2)
                    try:
                        image = bitmap.to_pil()
                        if box:
                            image = image.crop(
                                (
                                    int(box[0] * image.width),
                                    int(box[1] * image.height),
                                    int(box[2] * image.width),
                                    int(box[3] * image.height),
                                )
                            )
                        image.save(output / resource)
                    finally:
                        bitmap.close()
                        pdfpage.close()
                    resources.append(resource)
                    if not text.strip():
                        text = f"![未能转换的{kind}原图]({resource})"
                        bundle.issues.append(
                            {
                                "kind": "conversion_missing",
                                "page": number,
                                "block_type": kind,
                                "resource": resource,
                            }
                        )
                    if kind in {"image", "chart"}:
                        bundle.issues.append(
                            {
                                "kind": "chart_data_pending",
                                "page": number,
                                "resource": resource,
                                "message": "已保留原图；需确认是否为数据图并提取或登记不适用。",
                            }
                        )
                if not text.strip():
                    text = f"[未渲染内容：{kind}，请核对第 {number} 页]"
                    bundle.issues.append(
                        {"kind": "unrendered_block", "page": number, "block_type": kind}
                    )
                bundle.add(
                    text,
                    kind=kind,
                    locations=[location],
                    resources=list(dict.fromkeys(resources)),
                    engine_index=block.index,
                    continues_previous=getattr(block, "continues_prev", False),
                )
            if not page.blocks:
                resource = f"images/page-{number}-unrecognized.png"
                pdfpage = pdf[page.page_idx]
                bitmap = pdfpage.render(scale=1.5)
                try:
                    bitmap.to_pil().save(output / resource)
                finally:
                    bitmap.close()
                    pdfpage.close()
                bundle.add(
                    f"[第 {number} 页未识别到内容，请核对原页]",
                    locations=[{"page": number}],
                    resources=[resource],
                )
                bundle.issues.append({"kind": "empty_page", "page": number})
        if pages == "all" and seen != set(range(1, len(pdf) + 1)):
            raise RuntimeError("Parser omitted pages; incomplete bundle will not be activated")
        return bundle.finish(
            engine=f"mineru-{version('mineru')}-standard-onnx-llama-cpp",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            pages=sorted(seen),
            total_pages=len(pdf),
            full_document=pages == "all",
            normalized_rotations={str(i + 1): angle for i, angle in rotations.items()},
        )


def main():
    if os.environ.get("LITEXTRACT_PARSER_DIAGNOSTICS") == "1":
        import faulthandler

        faulthandler.dump_traceback_later(30, repeat=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--pages", default="all")
    parser.add_argument("--watch-parent", action="store_true")
    args = parser.parse_args()
    # Windows BLAS initialization must finish before the parent-monitor thread starts.
    import numpy  # noqa: F401

    if args.watch_parent:
        import subprocess
        import sys
        import threading

        def monitor_parent():
            if os.name == "nt":
                import ctypes
                import msvcrt
                import time

                # A blocking CRT read holds the stdin lock and deadlocks later DLL
                # initialization (NumPy/ONNX). Peek at the kernel pipe instead.
                handle = ctypes.c_void_p(msvcrt.get_osfhandle(sys.stdin.fileno()))
                while ctypes.windll.kernel32.PeekNamedPipe(handle, None, 0, None, None, None):
                    time.sleep(0.5)
                subprocess.run(
                    ["taskkill", "/PID", str(os.getpid()), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                while os.read(sys.stdin.fileno(), 1):
                    pass
            os._exit(1)

        threading.Thread(target=monitor_parent, daemon=True).start()
    for key in ("MINERU_API_URL", "MINERU_API_KEY"):
        os.environ.pop(key, None)
    parse_pdf(args.source.resolve(), args.output.resolve(), args.version, args.pages)


if __name__ == "__main__":
    main()
