from __future__ import annotations

from fastapi import APIRouter

from app.api.dto.health import HealthResponseDTO

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponseDTO)
def health() -> HealthResponseDTO:
    return HealthResponseDTO(status="ok", service="api")
