from __future__ import annotations

from pydantic import BaseModel


class HealthResponseDTO(BaseModel):
    status: str = "ok"
    service: str = "api"
