# Analytics Serving Gateway

> A portfolio project demonstrating **API Gateway**, **Kubernetes**, and **GitHub Actions CI/CD** patterns using a real analytics workload on ClickHouse.

[![CI/CD Pipeline](https://github.com/YOUR_GITHUB_USER/analytics-serving-gateway/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/YOUR_GITHUB_USER/analytics-serving-gateway/actions)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![ClickHouse](https://img.shields.io/badge/ClickHouse-24.8-yellow)
![Kubernetes](https://img.shields.io/badge/Kubernetes-1.31-326CE5)

---

## 🏗️ Architecture

```
[Client]
    │  Timestamp + Authorization: Bearer <sha256_token>
    ▼
[NGINX Gateway / Ingress] ← SSL Termination (HTTPS) + Subdomain Routing + Rate Limit (10 rps)
    │
    ▼
[K8s Deployment / Docker: FastAPI Backend]
    ├─ Analytics Router  (/api/v1/sales/*)     ← Verified against ANALYTICS_API_KEYS
    └─ Branding Router   (/api/v1/branding/*)  ← Verified against BRANDING_API_KEYS
    │
    ▼
[ClickHouse] ← OLAP queries (50K+ sample orders)
```

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (Python 3.12) |
| API Gateway | NGINX Ingress Controller |
| Container Orchestration | Kubernetes (Minikube for local) |
| CI/CD | GitHub Actions → GHCR → kubectl deploy |
| Database | ClickHouse (OLAP, docker-compose) |
| Autoscaling | HorizontalPodAutoscaler |

## 🚀 Quick Start

### Prerequisites
```bash
# Install tools
brew install minikube kubectl helm  # macOS
# OR
sudo apt install minikube kubectl   # Ubuntu

# Start Minikube
minikube start --memory 4096 --cpus 2

# Enable addons
minikube addons enable ingress
minikube addons enable metrics-server
```

### 1. Start ClickHouse (data layer)
```bash
docker compose up -d
# Wait for ClickHouse to init (~10s), then verify:
docker compose logs clickhouse | tail -5
```

### 2. Build & run locally (without K8s)
```bash
pip install -r api_app/requirements.txt
CLICKHOUSE_HOST=localhost \
ANALYTICS_API_KEYS="demo-key-123" \
BRANDING_API_KEYS="demo-key-123" \
uvicorn api_app.main:app --reload
# → http://localhost:8000/docs
```

### 3. Deploy to Kubernetes
```bash
# Build image
docker build -t analytics-api:local .

# Load into Minikube (skip push to registry for local dev)
minikube image load analytics-api:local

# Update deployment image to local tag
sed -i 's|ghcr.io/YOUR_GITHUB_USER/analytics-serving-gateway:latest|analytics-api:local|' \
  k8s/api-deployment.yaml

# Apply all manifests
kubectl apply -f k8s/

# Add to /etc/hosts
echo "$(minikube ip) analytics.local branding.local" | sudo tee -a /etc/hosts

# Test with SHA-256 + Timestamp signing!
NOW=$(date +%s)
TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')
curl -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN}" \
     http://analytics.local/api/v1/sales/daily?days=7
```

### 4. Test rate limiting
```bash
NOW=$(date +%s)
TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

# Send 25 rapid requests — exceeding rate limit should get HTTP 429 / 503
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Timestamp: ${NOW}" \
    -H "Authorization: Bearer ${TOKEN}" \
    http://analytics.local/api/v1/sales/daily
done
```

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Liveness probe (no auth required) |
| `GET` | `/readyz` | Readiness probe (checks DB) |
| `GET` | `/api/v1/sales/daily` | Daily sales summary (Analytics Service) |
| `GET` | `/api/v1/products/top` | Top products by revenue (Analytics Service) |
| `GET` | `/api/v1/regions/summary` | Sales by region (Analytics Service) |
| `GET` | `/api/v1/branding/overview` | Branding overview (Branding Service) |

All business endpoints require `Timestamp` and `Authorization: Bearer <sha256_token>` headers.

## 🔄 CI/CD Flow (GitHub Actions)

```
git push main
    │
    ├─ Job 1: test     → ruff lint + pytest (mocked DB)
    │
    ├─ Job 2: build    → docker build → push to GHCR
    │
    └─ Job 3: deploy   → kubectl apply + rollout wait
```

### Setup GitHub Secrets
```bash
# Generate kubeconfig secret
cat ~/.kube/config | base64 -w 0
# → Paste as KUBECONFIG_B64 in GitHub repo Settings → Secrets
```

## 📁 Project Structure

```
analytics-serving-gateway/
├── .github/workflows/ci-cd.yml   # GitHub Actions CI/CD pipeline
├── api_app/
│   ├── main.py                   # FastAPI app + middleware
│   ├── auth.py                   # Decentralized SHA-256 + Timestamp auth module
│   ├── database.py               # ClickHouse async client
│   ├── routers/
│   │   ├── analytics.py          # Analytics endpoints
│   │   └── branding.py           # Branding endpoints
│   └── requirements.txt
├── k8s/
│   ├── namespace.yaml            # K8s namespace
│   ├── configmap.yaml            # Non-sensitive app config (DB port, name, workers)
│   ├── secret.yaml.example       # API keys + DB credentials template
│   ├── api-deployment.yaml       # 2-replica Deployment
│   ├── api-service.yaml          # ClusterIP Service
│   ├── ingress.yaml              # NGINX Ingress (subdomain routing + SSL)
│   ├── network-policy.yaml       # K8s network isolation policy
│   └── hpa.yaml                  # Auto-scaling (2–5 Pods)
├── gateway/
│   └── nginx.conf                # NGINX Reverse Proxy + SSL Termination + Subdomain router
├── scripts/
│   ├── generate-ssl.sh           # Local self-signed SSL/TLS generator
│   └── init-clickhouse.sql       # Sample data (50K orders)
├── tests/test_api.py             # Pytest suite (mocked DB + Auth signing)
├── Dockerfile                    # Multi-stage build
├── docker-compose.yml            # ClickHouse, API Service, NGINX Gateway
└── README.md
```

## 📚 Concepts Learned

- **API Gateway pattern**: Rate limiting, auth, routing at the edge
- **K8s Deployment**: Pod lifecycle, rolling updates, health probes
- **K8s Service**: ClusterIP for internal service discovery
- **K8s Ingress**: NGINX as a reverse proxy / API gateway
- **K8s HPA**: Auto-scaling based on CPU metrics
- **K8s Secrets**: Secure credential injection
- **GitHub Actions**: Multi-job CI/CD with environment protection
- **Docker multi-stage builds**: Minimal production images
- **ClickHouse OLAP**: Columnar queries, MergeTree engine

