import json
import os
import queue
import subprocess
import sys
import threading

import httpx
import pytest


@pytest.mark.parametrize("shutdown", ["command", "parent_eof"])
def test_backend_process_lifecycle(tmp_path, shutdown):
    token = "lifecycle-test-token"
    child = subprocess.Popen(
        [sys.executable, "-m", "backend.runner"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "LITEXTRACT_DATA_DIR": str(tmp_path), "LITEXTRACT_API_TOKEN": token},
    )
    try:
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
        ready = json.loads(lines.get(timeout=20))
        assert ready["event"] == "ready"
        url = f"http://127.0.0.1:{ready['port']}/api/health"
        assert (
            httpx.get(
                url, headers={"Authorization": f"Bearer {token}"}, trust_env=False
            ).status_code
            == 200
        )
        if shutdown == "command":
            child.stdin.write("shutdown\n")
            child.stdin.flush()
        child.stdin.close()
        assert child.wait(timeout=10) == 0
        with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
            httpx.get(url, timeout=1, trust_env=False)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
