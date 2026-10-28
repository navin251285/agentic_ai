"""One command starts the whole app: python -m brightside_desk (or the brightside-desk script).

It serves the API and the one-page UI at http://127.0.0.1:8980/. The host and port come from APP_HOST and APP_PORT
(the course .env or the environment); --port overrides the port for one run, and --reload restarts on code changes.
Nothing is started at import time, so the tests can call main() with a fake server.
"""
from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from .config import load_settings

log = logging.getLogger("brightside_desk")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brightside-desk", description="Run the Brightside support desk locally.")
    parser.add_argument("--port", type=int, default=None, help="port to listen on (default: APP_PORT or 8980)")
    parser.add_argument("--reload", action="store_true", help="restart the server when the code changes (development)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()  # a bad APP_PORT or APP_HOST stops here, with the setting's name in the message
    port = args.port if args.port is not None else settings.port
    log.info("serving the desk on http://%s:%s/ (health: /health)", settings.host, port)
    uvicorn.run("brightside_desk.api:app", host=settings.host, port=port, reload=args.reload, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
