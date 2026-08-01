from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        duration_ms = int((perf_counter() - started) * 1000)
        response.headers["x-request-duration-ms"] = str(duration_ms)
        return response


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
