"""
Authentication module for Analytics & Branding Services (Option A: Decentralized Auth).

Chuẩn Production (HMAC-SHA256 chống Replay & Cross-Endpoint Replay):
  - Header 'Timestamp': Unix timestamp (giây). Giới hạn hiệu lực trong ±60 giây.
  - Header 'Authorization': 'Bearer <signature>' với:
        canonical = "{METHOD}:{PATH}:{TIMESTAMP}"   (VD: "GET:/api/v1/sales/daily:1795686000")
        signature = HMAC-SHA256(secret_key, canonical)
  - Secret key KHÔNG BAO GIỜ được gửi qua mạng và KHÔNG BAO GIỜ bị cắt/lộ ra response.
  - Mỗi service tự quản lý danh sách Key hợp lệ qua biến môi trường độc lập (Fail-Fast):
      * Service Analytics: ANALYTICS_API_KEYS
      * Service Branding: BRANDING_API_KEYS
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

logger = logging.getLogger("analytics-gateway.auth")

# Window thời gian hợp lệ cho Timestamp (mặc định 60 giây)
TIMESTAMP_TOLERANCE_SECONDS = 60.0


def compute_hmac_signature(secret_key: str, method: str, path: str, timestamp: str) -> str:
    """Tính chữ ký HMAC-SHA256 gắn chặt với HTTP method, path và timestamp."""
    canonical = f"{method.upper()}:{path}:{timestamp}".encode()
    return hmac.new(secret_key.encode(), canonical, hashlib.sha256).hexdigest()


def get_service_keys(env_var: str) -> set[str]:
    """
    Đọc danh sách keys hợp lệ của từng service từ biến môi trường riêng.
    Fail-Fast: Bắt buộc biến môi trường phải được cấu hình.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        raise RuntimeError(
            f"CRITICAL SECURITY CONFIGURATION: Environment variable '{env_var}' "
            f"is required and cannot be empty! Please configure it in your .env or K8s Secret."
        )
    return set(filter(None, [k.strip() for k in raw.split(",")]))


def require_service_auth(service_name: str, env_var: str):
    """
    Tạo dependency xác thực riêng biệt cho từng service.
    Mỗi service chỉ chấp nhận các key được cấu hình trong env_var của nó.
    """
    async def _verifier(
        request: Request,
        timestamp: Annotated[str | None, Header(alias="Timestamp")] = None,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> str:
        valid_keys = get_service_keys(env_var)

        # ── 1. KIỂM TRA HEADER TIMESTAMP ────────────────────────────────────
        if not timestamp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"Missing 'Timestamp' header for {service_name} service. "
                    "Production requires 'Timestamp' and 'Authorization: Bearer <hmac_sha256_signature>'."
                ),
            )

        try:
            req_ts = float(timestamp)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 'Timestamp' header format. Must be Unix timestamp in seconds.",
            )

        current_ts = time.time()
        diff = abs(current_ts - req_ts)
        if diff > TIMESTAMP_TOLERANCE_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"Timestamp expired or clock skewed. Allowed window: ±{TIMESTAMP_TOLERANCE_SECONDS}s, "
                    f"current diff: {diff:.1f}s."
                ),
            )

        # ── 2. TRÍCH XUẤT CHỮ KÝ TỪ AUTHORIZATION HEADER ────────────────────
        raw_token = ""
        if authorization:
            parts = authorization.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_token = parts[1].strip()
            elif len(parts) == 1:
                raw_token = parts[0].strip()

        if not raw_token:
            raw_token = request.headers.get("X-Token", "").strip()

        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"Missing token in Authorization header for {service_name} service. "
                    "Expected 'Authorization: Bearer <hmac_sha256_signature>'."
                ),
            )

        # ── 3. ĐỐI CHIẾU CHỮ KÝ HMAC-SHA256(key, METHOD:PATH:TIMESTAMP) ─────
        method = request.method.upper()
        path = request.url.path
        for secret_key in valid_keys:
            expected = compute_hmac_signature(secret_key, method, path, timestamp)
            if secrets.compare_digest(raw_token.lower(), expected.lower()):
                # Trả fingerprint một chiều (KHÔNG BAO GIỜ cắt hay làm lộ secret_key!)
                key_fingerprint = hashlib.sha256(secret_key.encode()).hexdigest()[:8]
                return f"client_{service_name}_{key_fingerprint}"

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unauthorized: HMAC signature is invalid or key has no permission for {service_name} service.",
        )

    return _verifier


# Dependencies tiện dụng cho từng router
AnalyticsAuth = Annotated[str, Depends(require_service_auth("analytics", "ANALYTICS_API_KEYS"))]
BrandingAuth = Annotated[str, Depends(require_service_auth("branding", "BRANDING_API_KEYS"))]
Auth = AnalyticsAuth
