"""Private desktop child process; stdin EOF also shuts down after a parent crash."""

import json
import os
import socket
import sys
import threading
import time

import uvicorn

from backend.main import create_app
from backend.parsers.docling_adapter import prepare_native_runtime


def run() -> None:
    prepare_native_runtime()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning", access_log=False))

        def watch_parent():
            if os.name == "nt":
                import ctypes
                import msvcrt

                handle = ctypes.c_void_p(msvcrt.get_osfhandle(sys.stdin.fileno()))
                available = ctypes.c_ulong()
                # A blocking CRT stdin read can stall later native DLL imports.
                while (
                    ctypes.windll.kernel32.PeekNamedPipe(
                        handle, None, 0, None, ctypes.byref(available), None
                    )
                    and not available.value
                ):
                    time.sleep(0.1)
            else:
                sys.stdin.readline()
            server.should_exit = True

        def announce():
            while not server.started and not server.should_exit:
                time.sleep(0.025)
            if server.started:
                print(json.dumps({"event": "ready", "port": listener.getsockname()[1]}), flush=True)

        threading.Thread(target=watch_parent, daemon=True).start()
        threading.Thread(target=announce, daemon=True).start()
        server.run(sockets=[listener])


if __name__ == "__main__":
    run()
