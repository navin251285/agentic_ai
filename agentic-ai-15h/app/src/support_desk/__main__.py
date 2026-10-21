"""python -m support_desk: start the whole app (the chat, the refund desk and the traces) on the port in SUPPORT_PORT.

One command, no Docker: the API serves the one-page UI at /, so there is nothing else to start.
"""
import logging

import uvicorn

from support_desk.settings import load_settings

logger = logging.getLogger("support_desk")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    port = load_settings().port
    logger.info("serving the support desk at http://127.0.0.1:%s/ (health: /health, Ctrl+C stops it)", port)
    uvicorn.run("support_desk.api:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
