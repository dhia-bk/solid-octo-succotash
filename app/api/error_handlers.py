from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import ProjectPulseError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProjectPulseError)
    async def project_pulse_error_handler(_: Request, exc: ProjectPulseError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": exc.message, "details": exc.context})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "validation_failed", "details": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "internal_server_error", "details": str(exc)})
