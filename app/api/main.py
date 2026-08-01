from __future__ import annotations

from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.middleware import register_middleware
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router

app = FastAPI(title="Project Pulse KG API", version="1.0.0")
register_middleware(app)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(users_router)


def main() -> None:
    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=False)
