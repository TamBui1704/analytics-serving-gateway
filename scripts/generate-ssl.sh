#!/bin/bash
# scripts/generate-ssl.sh
# Sinh chứng chỉ SSL tự ký (Self-signed) cho local HTTPS
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${DIR}/gateway/certs"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "${DIR}/gateway/certs/nginx.key" \
  -out "${DIR}/gateway/certs/nginx.crt" \
  -subj "/C=VN/ST=Hanoi/L=Hanoi/O=AnalyticsGateway/CN=analytics.local" \
  -addext "subjectAltName=DNS:analytics.local,DNS:branding.local,DNS:localhost,IP:127.0.0.1"

echo "✅ Đã tạo chứng chỉ SSL thành công tại gateway/certs/"

