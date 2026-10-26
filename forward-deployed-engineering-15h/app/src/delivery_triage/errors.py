"""One shape for every error the API returns: {"detail": "what happened", "code": "what kind"}.

The page shows `detail` to the support agent; the `code` is stable, so a script or a test can branch on it.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """An error the API answers on purpose, with an HTTP status, a stable code and a plain message."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        message = f"The request is not valid: {where} {first.get('msg', '')}".strip()
        return JSONResponse({"detail": message, "code": "invalid_request"}, status_code=422)
