"""Bounded child process with cancellation, and no automatic retry."""

import argparse
import os
import subprocess
import time
from pathlib import Path

from backend.core.errors import DomainError


def run_parser(source, output, *, cancel=None, timeout=1800, version=None, pages="all"):
    root = Path(__file__).resolve().parents[2]
    executable = Path(
        os.environ.get(
            "LITEXTRACT_MINERU_PYTHON", root / ".local/parser-next/venv/Scripts/python.exe"
        )
    )
    if not executable.is_file():
        raise DomainError("新版解析器环境尚未安装，请先准备 MinerU 独立运行环境。")
    # Embedded 3.13 keeps extension modules in its root. Never put that directory
    # on the separate 3.12 interpreter's search path or current working directory.
    child_root = executable.parent if (executable.parent / "backend").is_dir() else root
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=str(child_root),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        MINERU_HOME=environment.get("MINERU_HOME", str(root / ".local/parser-next/mineru-home")),
        HF_HOME=environment.get("HF_HOME", str(root / ".local/parser-next/huggingface")),
        LITEXTRACT_PARSER_MODELS=environment.get(
            "LITEXTRACT_PARSER_MODELS", str(root / ".local/parser-next/mineru-home/models")
        ),
        MINERU_MODEL_SOURCE="local",
        HF_HUB_OFFLINE="1",
    )
    for key in ("MINERU_API_URL", "MINERU_API_KEY"):
        environment.pop(key, None)
    command = [
        str(executable),
        "-m",
        "backend.parsing_next.mineru_worker",
        str(Path(source).resolve()),
        str(Path(output).resolve()),
        "--pages",
        pages,
        "--watch-parent",
    ]
    if version:
        command.extend(["--version", version])
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(str(output) + ".log").open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            env=environment,
            cwd=child_root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel and cancel.is_set():
                    raise DomainError("解析已取消，上一可用版本保留。")
                if time.monotonic() - started > timeout:
                    raise DomainError(f"解析超过 {timeout} 秒，已停止；未自动重试。")
                time.sleep(0.2)
            if process.returncode:
                raise DomainError(f"MinerU 解析退出码 {process.returncode}；请查看此次解析日志。")
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()
                process.wait(timeout=20)
            if process.stdin:
                process.stdin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    run_parser(args.source, args.output, timeout=args.timeout)
