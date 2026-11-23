"""
Branding service router (mô phỏng service độc lập thứ 2).
"""

from __future__ import annotations

from fastapi import APIRouter

from api_app.auth import BrandingAuth

router = APIRouter(prefix="/branding", tags=["Branding Service"])


@router.get("", summary="Branding Root")
@router.get("/overview", summary="Branding Service Overview")
async def branding_overview(client: BrandingAuth):
    """
    Endpoint của phân hệ Branding: chỉ chấp nhận các key trong BRANDING_API_KEYS.
    """
    return {
        "service": "Branding Service API",
        "status": "active",
        "message": "Welcome to Branding Hub!",
        "authenticated_client": client,
    }

