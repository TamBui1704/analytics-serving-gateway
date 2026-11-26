# 🎓 Giáo Trình Thực Hành 4 Nấc: Từ Docker, API Gateway, K8s đến Giám Sát (Observability)

Dự án này được thiết kế để bạn học từ gốc rễ đến nâng cao theo **4 Nấc thang**. Bạn sẽ không bị ngợp vì mỗi nấc giải quyết một bài toán duy nhất.

---

## 🎯 BẢN ĐỒ 4 NẤC HỌC TẬP

```
[ NẤC 1: DOCKER & BACKEND API ]
  👉 Học: Dockerfile là gì? Container giao tiếp ra sao?
  👉 Cổng test: http://localhost:8000
  👉 Không có Gateway, gọi thẳng vào FastAPI & ClickHouse.

            │ (Khi đã hiểu Docker & API)
            ▼
[ NẤC 2: API GATEWAY (NGINX THUẦN) ]
  👉 Học: Tại sao cần API Gateway? Edge Authentication & Rate Limiting hoạt động ra sao?
  👉 Cổng test: http://localhost:8080
  👉 Thấy tận mắt NGINX chặn đứng request xấu trước khi chạm tới FastAPI.

            │ (Khi đã hiểu API Gateway)
            ▼
[ NẤC 3: KUBERNETES & CI/CD (GITHUB ACTIONS) ]
  👉 Học: Chuyển NGINX thành Ingress Controller, FastAPI thành Deployment & Pods.
  👉 Tự động co giãn (HPA) và tự động build & deploy khi `git push`.

            │ (Mở rộng Observability trên Docker Compose — nhẹ máy, chuẩn kiến trúc thực tế)
            ▼
[ NẤC 4: GIÁM SÁT (METRICS), LOGGING & CẢNH BÁO (PLG + ALERTMANAGER) ]
  👉 Học: Prometheus + Alertmanager + Loki + Promtail + Grafana tách riêng file `docker-compose.monitoring.yml`.
  👉 Theo dõi tổng quan (req/s, latency p95, tỉ lệ lỗi) & soi chi tiết log NGINX + FastAPI bằng LogQL.
  👉 Kiểm thử quy tắc cảnh báo (Alert Rules) thực tế khi API gặp sự cố.
```

---

# 🚀 NẤC 1: Docker & Python API Thuần

### 1. Mục tiêu nấc này:
- Hiểu `Dockerfile` đóng gói mã nguồn Python như thế nào.
- Hiểu cách hai container (`clickhouse` và `api_service`) nói chuyện với nhau thông qua mạng ảo của Docker.

### 2. Khởi động Nấc 1:
Chạy lệnh sau để Docker tự động build code và kết nối ClickHouse:
```bash
docker compose up -d clickhouse api_service
```

### 3. Thực hành kiểm tra:
1. **Kiểm tra sức khỏe hệ thống (Health Check)**:
   ```bash
   curl http://localhost:8000/healthz
   # Trả về: {"status":"ok"}
   ```
2. **Kiểm tra API kết nối tới ClickHouse**:
   ```bash
   curl http://localhost:8000/readyz
   # Trả về: {"status":"ready","db":"clickhouse:ok"}
   ```
3. **Thử gọi API lấy báo cáo doanh thu theo ngày**:
   *(Truy vấn trực tiếp bảng orders chứa 50.000 bản ghi trên ClickHouse)*:
   ```bash
   NOW=$(date +%s)
   TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

   # Gọi kèm chữ ký SHA-256 + Timestamp (chuẩn bảo mật Production):
   curl -H "Timestamp: ${NOW}" \
        -H "Authorization: Bearer ${TOKEN}" \
        "http://localhost:8000/api/v1/sales/daily?days=7"
   ```

---

# 🚪 NẤC 2: API Gateway (NGINX Thuần)

### 1. Mục tiêu nấc này:
- Hiểu tại sao **không nên** để client gọi thẳng vào backend.
- Hiểu vai trò của **Edge Authentication**: Chặn request sai ngay tại cổng vào, không tốn tài nguyên của server backend.
- Hiểu vai trò của **Rate Limiting**: Chống spam và bảo vệ hệ thống khỏi bị quá tải.

### 2. Khởi động Nấc 2:

#### Bước 2.1: Tạo chứng chỉ SSL/TLS thủ công cho HTTPS (cho cả analytics.local và branding.local):
Trước khi bật NGINX, ta chạy script tạo cặp khóa RSA 2048-bit và chứng chỉ x509:
```bash
bash scripts/generate-ssl.sh
# Kết quả: Tự động sinh ra 2 file gateway/certs/nginx.crt và gateway/certs/nginx.key
```

#### Bước 2.2: Bật container `api_gateway`:
Bật container `api_gateway` (được mount thư mục `gateway/certs` và cấu hình HTTPS):
```bash
docker compose up -d api_gateway
```

Lúc này kiến trúc trở thành:
```
Client ──► Cổng 8080 (HTTP) hoặc 8443 (HTTPS) ──► NGINX Gateway ──► Cổng 8000 (FastAPI) ──► ClickHouse (8123)
```

### 3. Thực hành kiểm chứng các tính năng của Gateway:

> 🛡️ **Chuẩn bảo mật Production (Chữ ký SHA-256 + Timestamp):**
> Secret Key **KHÔNG BAO GIỜ** được gửi trực tiếp lên Header qua mạng.
> Thay vào đó, Client tính toán chữ ký số:
> `Token = sha256(secret_key + timestamp)` và gửi kèm `Timestamp` (hợp lệ trong 60 giây).

#### Thí nghiệm 2.1: Gọi bình thường qua Gateway (Thành công)
Tạo Token và gọi qua cổng **8080** (HTTP) hoặc **8443** (HTTPS):
```bash
# 1. Lấy Unix timestamp hiện tại (giây)
NOW=$(date +%s)

# 2. Tạo Token = SHA256(secret_key + timestamp) với key demo-key-123
TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

# 3. Gửi request kèm Timestamp và Token chữ ký:
curl -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN}" \
     "http://localhost:8080/api/v1/sales/daily?days=7"
```
👉 Bạn nhận được dữ liệu JSON, Secret Key được giữ kín an toàn trên máy client, và request đã đi qua NGINX trung gian.

#### Thí nghiệm 2.2: Test Edge Authentication (Chặn đứng khi thiếu hoặc sai xác thực)
Thử gửi request mà **KHÔNG** truyền Timestamp và Token:
```bash
curl -i http://localhost:8080/api/v1/sales/daily
```
👉 **Hiện tượng**: Hệ thống lập tức trả về:
```json
HTTP/1.1 401 Unauthorized
{"detail": "Missing 'Timestamp' header for analytics service. Production requires 'Timestamp' and 'Authorization: Bearer <sha256_token>'."}
```
*(Request bị từ chối ngay lập tức, bảo vệ an toàn cho cơ sở dữ liệu ClickHouse).*

#### Thí nghiệm 2.3: Test Rate Limiting (Chống Spam / DDoS)
Trong file [`gateway/nginx.conf`](gateway/nginx.conf), chúng ta quy định tốc độ **10 requests/giây**, cho phép chịu tải đột ngột với bộ đệm `burst=20`.
Hãy chạy vòng lặp gửi dồn dập 40 requests để làm cạn bộ đệm burst:
```bash
NOW=$(date +%s)
TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

for i in {1..40}; do
  curl -s -o /dev/null -w "Req $i: HTTP %{http_code}\n" \
    -H "Timestamp: ${NOW}" \
    -H "Authorization: Bearer ${TOKEN}" \
    http://localhost:8080/api/v1/sales/daily
done
```
👉 **Hiện tượng**: 
- Các request đầu (khoảng 1 đến 23): `HTTP 200` (được xử lý nhờ dung lượng `burst=20` ban đầu).
- Các request tiếp theo (từ 24 đến 40): Xuất hiện hàng loạt **`HTTP 503`** do NGINX Rate Limiting đã cạn buffer và chặn đứng request spam!

---

# 🌐 NẤC 2.5: Subdomain Routing + Phân Quyền Key Theo Dịch Vụ

> Đây là bài thực hành mở rộng sau khi bạn đã nắm vững Nấc 2.
> Mục tiêu: Trải nghiệm mô hình Gateway thực tế ở các dự án Production —
> **1 Gateway phục vụ nhiều dịch vụ, mỗi khách hàng chỉ vào được dịch vụ họ được cấp quyền**.

---

### 1. Mục tiêu bài thực hành này

- Hiểu cách NGINX phân luồng request theo **Subdomain** (`analytics.local`, `branding.local`).
- Hiểu kiến trúc **Decentralized Auth (Phân quyền phi tập trung)**: NGINX giữ vai trò L7 Reverse Proxy định tuyến trong sáng, xử lý SSL Termination (HTTPS) và Rate Limiting; từng Service tự quản lý danh sách Key được phép qua biến môi trường độc lập (`ANALYTICS_API_KEYS`, `BRANDING_API_KEYS`).
- Áp dụng chuẩn bảo mật Production: Xác thực bằng chữ ký số **SHA-256 + Timestamp** với cửa sổ hiệu lực 60 giây chống Replay Attack, tuyệt đối không gửi Secret Key thô qua đường mạng.

---

### 2. Kiến trúc bài thực hành (Option A: Decentralized Auth)

```
                            ┌───────────────────────────────────────────────┐
                            │          SERVER NGINX GATEWAY :8443 (HTTPS)   │
                            │                                               │
Client gọi vào ────────────►│  analytics.local ──► Proxy pass sang Backend  │
(Timestamp + Token SHA-256) │  branding.local  ──► Proxy pass sang Backend  │
                            │                                               │
                            │  * SSL Termination (TLS 1.2 / TLS 1.3)        │
                            │  * Rate Limit (10 req/s, burst 20)            │
                            └───────────────────────┬───────────────────────┘
                                                    │ (HTTP nội bộ)
                                                    ▼
                            ┌───────────────────────────────────────────────┐
                            │               FASTAPI BACKEND                 │
                            │                                               │
                            │  /api/v1/sales/*     (Router Analytics)       │
                            │    └─ Kiểm tra: key in ANALYTICS_API_KEYS     │
                            │                                               │
                            │  /api/v1/branding/*  (Router Branding)        │
                            │    └─ Kiểm tra: key in BRANDING_API_KEYS      │
                            └───────────────────────────────────────────────┘
```

**Bảng ma trận phân quyền khách hàng:**

| Khách hàng | Secret Key | Quyền gọi `analytics.local` | Quyền gọi `branding.local` |
|:---|:---:|:---:|:---:|
| Khách A | `key_user_a` | ✅ Được phép | ❌ Bị chặn (401) |
| Khách B | `key_user_b` | ❌ Bị chặn (401) | ✅ Được phép |
| Khách VIP | `key_user_vip` | ✅ Được phép | ✅ Được phép |

---

### 3. Giải thích file cấu hình [`gateway/nginx.conf`](gateway/nginx.conf)

NGINX hoạt động như một L7 Router thuần túy, an toàn và tối ưu hiệu năng:
1. **SSL Termination:** Lắng nghe trên cổng `8443` (HTTPS) với chuẩn `TLSv1.2 TLSv1.3`.
2. **Subdomain Routing:**
   - Block `server_name analytics.local;` định tuyến traffic tới Router Analytics (`/api/v1/sales/*`).
   - Block `server_name branding.local;` định tuyến traffic tới Router Branding (`/api/v1/branding/*`).
3. **Chuyển tiếp đầy đủ Header:** NGINX giữ nguyên các header xác thực (`Timestamp`, `Authorization`) và gán thêm các header chuẩn (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`) cho Backend.
4. **Không phụ thuộc file phân quyền phức tạp:** Khi cần cấp/hủy quyền khách hàng, ta chỉ cần thay đổi biến môi trường ở Backend (`ANALYTICS_API_KEYS`, `BRANDING_API_KEYS`), hoàn toàn không cần can thiệp hay reload NGINX Gateway.

---

### 4. Thiết lập môi trường test

Vì chúng ta không mua tên miền thật, ta dùng file `/etc/hosts` để trỏ hai domain nội bộ về máy mình:

#### Bước 4.1 — Thêm tên miền giả vào `/etc/hosts`

```bash
echo "127.0.0.1 analytics.local branding.local" | sudo tee -a /etc/hosts
```

Kiểm tra lại (phải thấy dòng vừa thêm ở cuối):
```bash
tail -3 /etc/hosts
# 127.0.0.1 analytics.local branding.local
```

#### Bước 4.2 — Khởi động toàn bộ stack Docker

```bash
# Khởi động cụm Docker (ClickHouse, FastAPI Backend, NGINX Gateway):
docker compose up -d
```

---

### 5. Thực hành bằng Terminal (curl với Chữ ký SHA-256 + Timestamp)

> 🛡️ **Chuẩn bảo mật Production:** 
> Secret Key **KHÔNG BAO GIỜ** được gửi thẳng trên Header qua đường mạng.
> Thay vào đó, Client tính toán chữ ký số:
> `Token = sha256(secret_key + timestamp)` và gửi kèm header `Timestamp` (hợp lệ trong 60 giây).

#### Thí nghiệm 2.5.1 — Khách A (`key_user_a`: chỉ có quyền Analytics)

```bash
# 1. Tính toán chữ ký SHA-256 cho Khách A
NOW=$(date +%s)
TOKEN_A=$(echo -n "key_user_a${NOW}" | sha256sum | awk '{print $1}')

# ✅ THÀNH CÔNG (200 OK): key_user_a có quyền gọi Analytics
curl -k -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN_A}" \
     "https://analytics.local:8443/api/v1/sales/daily?days=7"

# ❌ BỊ CHẶN (401 Unauthorized): key_user_a KHÔNG có quyền gọi Branding
curl -k -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN_A}" \
     "https://branding.local:8443/api/v1/branding/overview"
```

#### Thí nghiệm 2.5.2 — Khách B (`key_user_b`: chỉ có quyền Branding)

```bash
# 1. Tính toán chữ ký SHA-256 cho Khách B
NOW=$(date +%s)
TOKEN_B=$(echo -n "key_user_b${NOW}" | sha256sum | awk '{print $1}')

# ❌ BỊ CHẶN (401 Unauthorized): key_user_b KHÔNG có quyền gọi Analytics
curl -k -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN_B}" \
     "https://analytics.local:8443/api/v1/sales/daily?days=7"

# ✅ THÀNH CÔNG (200 OK): key_user_b có quyền gọi Branding
curl -k -H "Timestamp: ${NOW}" \
     -H "Authorization: Bearer ${TOKEN_B}" \
     "https://branding.local:8443/api/v1/branding/overview"
```

#### Thí nghiệm 2.5.3 — Khách VIP (`key_user_vip`: có quyền trên cả hai dịch vụ)

```bash
# 1. Tính toán chữ ký SHA-256 cho Khách VIP
NOW=$(date +%s)
TOKEN_VIP=$(echo -n "key_user_vip${NOW}" | sha256sum | awk '{print $1}')

# ✅ THÀNH CÔNG trên cả hai dịch vụ (200 OK)
curl -k -H "Timestamp: ${NOW}" -H "Authorization: Bearer ${TOKEN_VIP}" \
     "https://analytics.local:8443/api/v1/sales/daily?days=7"

curl -k -H "Timestamp: ${NOW}" -H "Authorization: Bearer ${TOKEN_VIP}" \
     "https://branding.local:8443/api/v1/branding/overview"
```

#### Thí nghiệm 2.5.4 — Kẻ xấu dùng key giả hoặc Timestamp quá hạn

```bash
# Kẻ xấu dùng token giả mạo:
curl -k -i -H "Timestamp: $(date +%s)" \
     -H "Authorization: Bearer fake_sha256_token_123456" \
     "https://analytics.local:8443/api/v1/sales/daily"
# ❌ Trả về: HTTP/1.1 401 Unauthorized

# Gửi Timestamp cũ quá hạn (> 60 giây - chống Replay Attack):
curl -k -i -H "Timestamp: 1600000000" \
     -H "Authorization: Bearer ${TOKEN_A}" \
     "https://analytics.local:8443/api/v1/sales/daily"
# ❌ Trả về: HTTP/1.1 401 Unauthorized (Timestamp expired)
```

---

### 6. Thực hành bằng Postman (GUI)

Để gửi chữ ký SHA-256 tự động trên Postman mà không phải tính tay:

#### Bước 6.1 — Cài đặt Pre-request Script trong Postman:
Vào tab **Pre-request Script** của Request hoặc Collection, dán đoạn mã JavaScript sau:

```javascript
// 1. Lấy Unix timestamp hiện tại (giây)
const timestamp = Math.floor(Date.now() / 1000);
pm.variables.set("timestamp", timestamp);

// 2. Tính SHA256(secret_key + timestamp)
const secretKey = "key_user_a"; // hoặc key_user_b, key_user_vip
const token = CryptoJS.SHA256(secretKey + timestamp).toString();
pm.variables.set("token", token);
```

#### Bước 6.2 — Cài đặt Headers trong Postman:
Chuyển sang tab **Headers**, thêm 2 headers:

| Key | Value |
|---|---|
| `Timestamp` | `{{timestamp}}` |
| `Authorization` | `Bearer {{token}}` |

Bấm **Send** $\rightarrow$ Postman sẽ tự động tính toán token SHA-256 mới cho mỗi lần bấm!

---

### 7. Cách thêm / thu hồi quyền một khách hàng

Trong mô hình **Phân quyền phi tập trung (Decentralized Auth - Phương án A)**:
Việc quản lý quyền thuộc về từng Service thông qua biến môi trường (Config/Secret), **hoàn toàn không cần sửa NGINX hay restart Gateway**:

- File [`docker-compose.yml`](docker-compose.yml):
  ```yaml
  # Muốn cấp quyền cho Khách C vào Analytics:
  ANALYTICS_API_KEYS: "key_user_a,key_user_vip,key_user_c"

  # Muốn thu hồi quyền của Khách A:
  ANALYTICS_API_KEYS: "key_user_vip,key_user_c"
  ```
- Trên Kubernetes: Chỉ cần cập nhật Kubernetes Secret (`ANALYTICS_API_KEYS` trong Secret của service), không cần cấu hình lại Ingress.

---

### 8. Dọn dẹp sau khi thực hành

Nếu bạn không muốn giữ `/etc/hosts` đã sửa:
```bash
# Xem nội dung file, tìm dòng cần xóa
cat /etc/hosts

# Xóa đúng dòng đã thêm
sudo sed -i '/analytics.local branding.local/d' /etc/hosts
```

---

# ☸️ NẤC 3: Kubernetes (K8s) & GitHub Actions (CI/CD)

Khi bạn đã hiểu bản chất ở Nấc 1 & Nấc 2, bạn sẽ thấy Nấc 3 thực chất là **chuyển đổi các khái niệm trên sang nền tảng K8s để có khả năng tự động hóa và chịu tải cao**:

| Nấc 2 (Docker thuần) | Nấc 3 (Kubernetes) | Vai trò |
|----------------------|-------------------|---------|
| `api_gateway (NGINX)` | **NGINX Ingress** (`k8s/ingress.yaml`) | Cổng API Gateway, Rate Limit, Edge Auth |
| `docker-compose.yml` | **K8s Service** (`k8s/api-service.yaml`) | Cân bằng tải nội bộ |
| `api_service (1 container)` | **K8s Deployment** (`k8s/api-deployment.yaml`) | Chạy nhiều Pods song song, tự phục hồi khi crash |
| Không có | **HPA** (`k8s/hpa.yaml`) | Tự động tăng Pods khi CPU cao |
| Chạy `docker build` bằng tay | **GitHub Actions** (`.github/workflows/ci-cd.yml`) | Tự động test, build image và deploy khi push code |

---

### 1. Kiến trúc K8s trong dự án này kết nối ra sao?

```
[ Người dùng / Client bên ngoài ]
               │ (Host: analytics.local)
               ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. INGRESS (k8s/ingress.yaml)                               │
│    - Bản chất là NGINX Ingress Controller                   │
│    - SSL Termination, Subdomain Routing, Rate Limiting      │
│    - Chuyển tiếp request vào Service tương ứng              │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Port 80)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. SERVICE (k8s/api-service.yaml - analytics-api-svc)       │
│    - Tạo ra 1 IP ảo nội bộ (ClusterIP) và tên miền DNS      │
│    - Đóng vai trò cân bằng tải (Load Balancer)              │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
    ┌────────────────────┐          ┌────────────────────┐
    │ 3. POD 1 (FastAPI) │          │ 3. POD 2 (FastAPI) │
    │   Port 8000        │          │   Port 8000        │
    └────────────────────┘          └────────────────────┘
               ▲                               ▲
               └───────────────┬───────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │ 4. DEPLOYMENT (k8s/api-deployment)  │
            │    - Quản lý số lượng Pod (luôn = 2)│
            │    - Tự bật lại Pod mới nếu Pod chết│
            │    - RollingUpdate: deploy 0s chết  │
            │    - Kiểm tra healthz / readyz      │
            └─────────────────────────────────────┘
                               ▲
                               │ Tự động tăng/giảm Pod (2 ◄──► 5)
            ┌──────────────────┴──────────────────┐
            │ 5. HPA (k8s/hpa.yaml)               │
            │    - CPU > 60% ──► Đẻ thêm Pod      │
            │    - Hết tải   ──► Giảm về 2 Pod    │
            └─────────────────────────────────────┘
```

---

### 2. Chuẩn bị môi trường thực hành K8s (Dùng Minikube)

Để chạy K8s ngay trên máy tính của bạn (không tốn tiền mua Cloud):

#### Bước 2.1: Cài đặt `kubectl` và `minikube` (nếu chưa có)
```bash
# 1. Cài kubectl (công cụ gõ lệnh điều khiển K8s)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 2. Cài Minikube (giả lập 1 cụm K8s mini ngay trong Docker máy bạn)
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

#### Bước 2.2: Khởi động Minikube và bật các Addon cần thiết
```bash
# Bật Minikube chạy bằng driver docker
minikube start --driver=docker --preload=false

# Bật NGINX Ingress Controller (để dùng k8s/ingress.yaml)
minikube addons enable ingress

# Bật Metrics Server (để HPA đo được % CPU)
minikube addons enable metrics-server
```

#### Bước 2.3: Chuẩn bị Docker Image cho K8s (2 Cách: Máy Local hoặc Đẩy lên Git/GHCR)

Để K8s có thể chạy được Pod FastAPI, nó cần lấy Docker Image từ một nơi nào đó. Bạn có thể chọn **1 trong 2 cách** sau tùy nhu cầu:

---

##### 🟢 CÁCH 1: Chạy Image trực tiếp từ máy (Nhanh nhất khi Dev/Test Local - Không cần đẩy lên mạng)

Cách này phù hợp khi bạn đang viết code trên máy, muốn kiểm thử ngay mà không cần kết nối Internet hay tạo tài khoản GitHub Container Registry:

1. **Build image từ mã nguồn hiện tại:**
   ```bash
   docker build -t analytics-api:latest .
   ```
2. **Nạp thẳng image từ Docker host vào cụm Minikube:**
   ```bash
   minikube image load analytics-api:latest
   ```
   *(Kiểm tra xem Minikube đã nhận image chưa: `minikube image ls | grep analytics-api`)*

3. **Cập nhật file `k8s/api-deployment.yaml`:**
   Mở file `k8s/api-deployment.yaml` (khoảng dòng 44-45), sửa phần `image` thành:
   ```yaml
   image: analytics-api:latest
   imagePullPolicy: Never   # Bắt K8s dùng ngay image nội bộ vừa nạp, không tìm trên mạng
   ```

---

##### 🚀 CÁCH 2: Đẩy Image lên GitHub Container Registry (GHCR) rồi cho K8s kéo về (Chuẩn Production / CI-CD)

> 💡 **Khái niệm:** Git chỉ quản lý mã nguồn (code). Docker image là file binary đóng gói nên được lưu trữ tại **Container Registry**. GitHub cung cấp sẵn dịch vụ Registry miễn phí tại địa chỉ `ghcr.io` (GitHub Container Registry).

Bạn có thể đưa image lên GHCR bằng **2 phương pháp**:

###### Phương pháp A: Tự động hoàn toàn bằng GitHub Actions (Khuyên dùng)
Dự án đã có sẵn pipeline CI/CD tại `.github/workflows/ci-cd.yml`:
1. Bạn chỉ cần commit và đẩy mã nguồn lên nhánh `main` của GitHub repo của bạn:
   ```bash
   git add .
   git commit -m "feat: setup k8s deployment"
   git push origin main
   ```
2. GitHub Actions sẽ tự động: Chạy test ruff/pytest ➔ Build Docker Image ➔ Đăng nhập GHCR ➔ Đẩy image lên `ghcr.io/<your-github-username>/analytics-serving-gateway:latest`.
3. Bạn vào mục **Packages** trên trang cá nhân GitHub, chuyển quyền hiển thị của Package sang **Public** (để Minikube kéo về không bị hỏi mật khẩu).

###### Phương pháp B: Build và Push bằng tay từ Terminal máy bạn
Nếu muốn chủ động đẩy bằng tay từ máy tính:
1. **Tạo GitHub Token (PAT):**
   * Vào GitHub ➔ **Settings** ➔ **Developer settings** ➔ **Personal access tokens (Tokens classic)** ➔ **Generate new token**.
   * Tích chọn quyền: `write:packages`, `read:packages`, `delete:packages`.
2. **Đăng nhập Docker vào GHCR trên terminal máy bạn:**
   ```bash
   echo "PAT_TOKEN_VỪA_TẠO" | docker login ghcr.io -u <tên_github_viết_thường> --password-stdin
   ```
3. **Build và gắn thẻ (Tag) đúng chuẩn (Lưu ý: Tên username BẮT BUỘC viết thường):**
   ```bash
   # Ví dụ username github của bạn là: tambt
   docker build -t ghcr.io/<tên_github_viết_thường>/analytics-serving-gateway:latest .
   ```
4. **Đẩy (Push) image lên GitHub:**
   ```bash
   docker push ghcr.io/<tên_github_viết_thường>/analytics-serving-gateway:latest
   ```
5. **Cập nhật file `k8s/api-deployment.yaml`:**
   Mở file `k8s/api-deployment.yaml`, điền tên image thật của bạn:
   ```yaml
   image: ghcr.io/<tên_github_viết_thường>/analytics-serving-gateway:latest
   imagePullPolicy: Always
   ```
   *(Nếu Package ở chế độ Private, xem thêm hướng dẫn tạo `imagePullSecret` trong tài liệu).*

---

### 3. Phân biệt Cấu hình (ConfigMap) và Bảo mật (Secret) & Triển khai lên K8s

> 💡 **Triết lý 12-Factor App & An toàn thông tin:**
> * **ConfigMap (`k8s/configmap.yaml`):** Lưu trữ cấu hình **KHÔNG nhạy cảm** (Port `8123`, DB `analytics`, số `WORKERS`, danh sách `CORS_ORIGINS`). File này **an toàn 100% để commit lên Git**.
> * **Secret (`k8s/secret.yaml`):** Lưu trữ thông tin **NHẠY CẢM** (API Keys, Mật khẩu Database, Chứng chỉ SSL). File này **BẮT BUỘC nằm trong `.gitignore`** để tránh rò rỉ lên mạng.
> * **File mẫu (`k8s/secret.yaml.example`):** Là bản vẽ thiết kế mẫu (Template) chứa key mẫu, được đẩy lên Git để các thành viên khác trong team biết cần phải điền những biến môi trường bí mật nào khi dựng dự án.
>
> Trong `k8s/api-deployment.yaml`, cả ConfigMap và Secret được nạp đồng thời vào Pod thông qua khối `envFrom`:
> ```yaml
> envFrom:
>   - configMapRef:
>       name: analytics-gateway-config
>   - secretRef:
>       name: analytics-gateway-secret
> ```

---

#### Các bước triển khai thực tế theo đúng thứ tự:

##### Bước 3.1: Đảm bảo Database ClickHouse đang chạy trên Docker máy bạn
Vì ứng dụng FastAPI có tính năng kiểm tra sức khỏe (*Readiness Probe* gọi `/readyz`), nếu ClickHouse chưa bật thì Pod K8s sẽ báo lỗi 503 và từ chối nhận request:
```bash
docker compose up -d clickhouse
```

##### Bước 3.2: Áp dụng các file cấu hình K8s
```bash
# 1. Tạo "khu vực riêng" (Namespace) cho dự án
kubectl apply -f k8s/namespace.yaml

# 2. Tạo ConfigMap (Cấu hình chung: Port, DB Name, CORS...)
kubectl apply -f k8s/configmap.yaml -n analytics

# 3. Tạo Secret (Khóa bí mật: API Keys, Host, Password...)
# Có 2 cách tạo Secret:
#
# Cách A (Khuyên dùng - Nhanh gọn qua CLI):
kubectl create secret generic analytics-gateway-secret \
  --from-literal=ANALYTICS_API_KEYS="key_user_a,key_user_vip,demo-key-123" \
  --from-literal=BRANDING_API_KEYS="key_user_b,key_user_vip" \
  --from-literal=CLICKHOUSE_HOST="host.minikube.internal" \
  --from-literal=CLICKHOUSE_PASSWORD="" \
  -n analytics \
  --dry-run=client -o yaml | kubectl apply -f -
#
# Cách B (Dùng file YAML):
# cp k8s/secret.yaml.example k8s/secret.yaml
# kubectl apply -f k8s/secret.yaml -n analytics

# 4. Tạo Deployment (Khởi chạy 2 Pod FastAPI tự động nạp ConfigMap & Secret)
kubectl apply -f k8s/api-deployment.yaml

# 5. Tạo Service (Bộ cân bằng tải nội bộ)
kubectl apply -f k8s/api-service.yaml

# 5.5 Tạo Secret TLS chứa chứng chỉ SSL cho HTTPS (BẮT BUỘC trước khi tạo Ingress):
kubectl create secret tls gateway-tls-secret \
  --cert=gateway/certs/nginx.crt \
  --key=gateway/certs/nginx.key \
  -n analytics

# 6. Tạo Ingress (API Gateway NGINX)
kubectl apply -f k8s/ingress.yaml

# 7. Tạo HPA (Tự động co giãn theo CPU)
kubectl apply -f k8s/hpa.yaml

# 8. Tạo NetworkPolicy (Tường lửa nội bộ cô lập Pod)
kubectl apply -f k8s/network-policy.yaml
```

##### Bước 3.3: Kiểm tra Pod đã nhận đủ cấu hình từ ConfigMap & Secret chưa
```bash
# Lấy tên một Pod đang chạy
POD_NAME=$(kubectl get pods -n analytics -l app=analytics-api -o jsonpath="{.items[0].metadata.name}")

# Kiểm tra các biến môi trường bên trong Pod
kubectl exec -it $POD_NAME -n analytics -- env | grep -E "CLICKHOUSE|API_KEY|CORS"
```
*(Bạn sẽ thấy cả biến từ ConfigMap như `CLICKHOUSE_PORT`, `CORS_ORIGINS` và biến từ Secret như `ANALYTICS_API_KEYS`, `CLICKHOUSE_HOST` đều đã hiện diện đầy đủ bên trong Pod).*

---

### 4. Các lệnh kiểm tra "thần thánh" cần biết trong K8s

Tất cả các tài nguyên đều nằm trong namespace `analytics`, nên thêm `-n analytics`:

```bash
# Xem toàn bộ tài nguyên đang chạy: Pod, Service, Deployment
kubectl get all -n analytics

# Xem chi tiết các Pod (IP, số lần restart, trạng thái)
kubectl get pods -n analytics -o wide

# Xem log trực tiếp của một Pod (thay tên pod thực tế từ lệnh trên)
kubectl logs -f -n analytics deployment/analytics-api

# Soi "bệnh án" của Pod khi bị lỗi (rất hay dùng khi Pod không chịu chạy)
kubectl describe pod <tên-pod> -n analytics
```

---

### 5. Thực hành các kịch bản thực tế chỉ K8s mới có

#### Kịch bản 1: Thử nghiệm khả năng tự phục hồi (Self-Healing)
* Giả lập sự cố: Có 1 Pod bị crash hoặc hacker phá hoại, bạn hãy thử tay "giết" một Pod:
  ```bash
  # Lấy danh sách tên pod
  kubectl get pods -n analytics

  # Xóa cưỡng bức 1 Pod
  kubectl delete pod <tên-pod-analytics-api-xxx> -n analytics
  ```
* **Hiện tượng:** Bạn gõ ngay `kubectl get pods -n analytics`, bạn sẽ thấy K8s đã **ngay lập tức sinh ra một Pod mới thay thế trong 1 giây** để luôn duy trì đủ 2 Pod như bạn yêu cầu!

#### Kịch bản 2: Cập nhật ứng dụng không gián đoạn (Zero-Downtime Rolling Update)
* Khi bạn sửa code và build image `analytics-api:v2`, bạn cập nhật Deployment:
  ```bash
  kubectl set image deployment/analytics-api api=analytics-api:v2 -n analytics
  ```
* **Hiện tượng:** K8s sẽ bật Pod mới phiên bản v2 lên trước. Khi Pod v2 vượt qua bài kiểm tra `/healthz` và `/readyz` an toàn, K8s mới bắt đầu tắt dần Pod v1 cũ. Người dùng gọi API liên tục sẽ **không bị rớt một request nào**!

#### Kịch bản 3: Thử nghiệm gọi qua Ingress Gateway trên Minikube

> ⚠️ **LƯU Ý CỰC KỲ QUAN TRỌNG VỀ CỔNG (PORT):**
> * **Ở Nấc 2 (Docker Compose NGINX):** Cổng HTTPS là `:8443` và HTTP là `:8080`.
> * **Ở Nấc 3 (Kubernetes Ingress):** Sử dụng các cổng tiêu chuẩn của Web:
>   * HTTP chạy trên cổng **`80`** (không cần gõ `:80`).
>   * HTTPS chạy trên cổng **`443`** (không cần gõ `:443`).
>   * ❌ **TUYỆT ĐỐI KHÔNG GÕ CỔNG `:8443`** trên Minikube! Vì trên Minikube, cổng `8443` là của **Kubernetes API Server** (nếu gọi vào đây bạn sẽ bị K8s báo lỗi `401 Unauthorized`).

1. **Lấy địa chỉ IP của cụm Minikube:**
   ```bash
   minikube ip
   # Ví dụ: 192.168.49.2
   ```

2. **Cập nhật IP Minikube vào `/etc/hosts` cho 2 tên miền `analytics.local` và `branding.local`:**
   ```bash
   echo "$(minikube ip) analytics.local branding.local" | sudo tee -a /etc/hosts
   ```

3. **Gọi API bằng HTTPS bảo mật SSL (Chuẩn Production - Port 443):**
   ```bash
   NOW=$(date +%s)
   TOKEN_A=$(echo -n "key_user_a${NOW}" | sha256sum | awk '{print $1}')

   curl -k -H "Timestamp: ${NOW}" \
        -H "Authorization: Bearer ${TOKEN_A}" \
        "https://analytics.local/api/v1/sales/daily?days=7"
   ```
   *(Request đi qua: Ingress NGINX (Chấm dứt SSL) ──► Service (ClusterIP) ──► chia tải ngẫu nhiên vào 1 trong 2 Pod FastAPI!)*

4. **Kiểm chứng tính năng Ép buộc chuyển hướng HTTPS (HTTP 308 Permanent Redirect):**
   Nếu người dùng hoặc client cố tình gọi qua `http://` thông thường:
   ```bash
   curl -I "http://analytics.local/api/v1/sales/daily?days=7"
   ```
   **Kết quả:** Ingress sẽ không trả dữ liệu thô mà lập tức phản hồi mã **`HTTP/1.1 308 Permanent Redirect`** kèm Header `Location: https://analytics.local/...` để ép client chuyển sang HTTPS!

---

### 6. Dọn dẹp sau khi thực hành K8s

Khi thực hành xong, muốn giải phóng RAM/CPU của máy tính:
```bash
# Xóa toàn bộ tài nguyên của dự án
kubectl delete namespace analytics

# Dừng cụm Minikube
minikube stop
```

---

# 📊 NẤC 4: Giám Sát (Metrics), Ghi Log Tập Trung (Loki) & Cảnh Báo (Alertmanager) trên Docker Compose

### 1. Kiến trúc & Triết lý tách file (Chuẩn thực tế)

Thay vì nhồi toàn bộ công cụ giám sát vào `docker-compose.yml` của ứng dụng, ta tách riêng thành **`docker-compose.monitoring.yml`** và kết nối chung vào mạng `analytics_net`:

```
  [ api_gateway (NGINX) ] ─── stdout/stderr logs ───┐
                                                    ▼
  [ api_service (FastAPI) ] ── stdout/stderr logs ─► [ Promtail ] ── push ──► [ Loki (:3100) ]
            │                                                                       │
            └── GET /metrics (15s/lần) ──► [ Prometheus (:9090) ]                   │
                                                    │        │                      │
                                     (Alert Rules)  │        └───────┐      ┌───────┘
                                                    ▼                ▼      ▼
                                        [ Alertmanager (:9093) ]   [ Grafana (:3000) ]
```

**Cấu trúc thư mục cấu hình (`monitoring/`):**
- `monitoring/prometheus/prometheus.yml`: Khai báo target cần scrape (`api_service:8000/metrics`) và kết nối Alertmanager.
- `monitoring/prometheus/alert_rules.yml`: Các luật cảnh báo (`AnalyticsApiDown`, `AnalyticsApiHighErrorRate`, `AnalyticsApiHighLatency`).
- `monitoring/alertmanager/alertmanager.yml`: Luật gom nhóm và định tuyến cảnh báo (receiver).
- `monitoring/loki/loki-config.yaml`: Cấu hình lưu trữ log trên filesystem (schema v13, retention mặc định `168h` = 7 ngày; muốn 3 tháng chỉ cần đổi thành `2160h`).
- `monitoring/promtail/promtail-config.yaml`: Tự động phát hiện các Docker container của dự án qua `/var/run/docker.sock`, gắn nhãn `service`, `container` và đẩy log về Loki.
- `monitoring/grafana/provisioning/`: Tự động khai báo sẵn 2 datasource (**Prometheus** & **Loki**) và nạp sẵn Dashboard **Analytics Serving Gateway - Overview & Logs**.

---

### 2. Khởi động hệ thống App + Monitoring

> **Lưu ý:** Nếu trước đó bạn có bật Minikube, hãy tắt (`minikube stop`) để giải phóng RAM cho máy.

```bash
# Chạy đồng thời App (ClickHouse + FastAPI + NGINX) và bộ Giám sát (5 container)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d --build

# Kiểm tra toàn bộ 8 container đang chạy
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml ps
```

**Danh sách giao diện web:**
| Công cụ | URL | Tài khoản |
| :--- | :--- | :--- |
| **Grafana** (Dashboard & Xem Log) | http://localhost:3000 | `admin` / `admin` |
| **Prometheus** (Targets, PromQL, Alerts) | http://localhost:9090 | Không cần |
| **Alertmanager** (Danh sách cảnh báo đang bắn) | http://localhost:9093 | Không cần |
| **FastAPI Metrics thô** | http://localhost:8000/metrics | Không cần |

---

### 3. Thực hành 1: Tạo lưu lượng & Xem Metrics tổng quan trên Grafana

1. Bắn vài request hợp lệ và vài request sai chữ ký (tạo lỗi `401`/`404`) vào API Gateway để có dữ liệu:
   ```bash
   # Request hợp lệ (200 OK)
   for i in {1..5}; do
     NOW=$(date +%s)
     TOKEN=$(echo -n "key_user_a${NOW}" | sha256sum | awk '{print $1}')
     curl -s -o /dev/null -w "200-test: %{http_code}\n" \
       -H "Timestamp: ${NOW}" \
       -H "Authorization: Bearer ${TOKEN}" \
       "http://localhost:8080/api/v1/sales/daily?days=7"
   done

   # Request sai token (401 Unauthorized) để thấy biểu đồ lỗi tăng lên
   for i in {1..3}; do
     curl -s -o /dev/null -w "401-test: %{http_code}\n" \
       "http://localhost:8080/api/v1/sales/daily?days=7"
   done
   ```
2. Mở **Grafana** tại http://localhost:3000 → đăng nhập `admin` / `admin`.
3. Vào **Dashboards → Analytics Gateway → Analytics Serving Gateway - Overview & Logs**.
4. Quan sát các biểu đồ cập nhật realtime:
   - **API Status**: `UP` (xanh lá)
   - **Request Rate (req/s)** phân tách theo từng endpoint (`/api/v1/sales/daily`) và mã trạng thái (`200`, `401`)
   - **Latency Percentiles (p50 / p95)**
   - **Live Logs** ở bảng dưới cùng hiển thị trực tiếp log từ `api_service` và `api_gateway`.

---

### 4. Thực hành 2: Soi log chi tiết bằng LogQL (Loki)

Trên Grafana, vào menu **Explore** (biểu tượng la bàn) → chọn Data source là **Loki**, thử các câu truy vấn sau:

```logql
# Xem toàn bộ log của FastAPI (api_service)
{service="api_service"}

# Xem toàn bộ log của NGINX API Gateway (api_gateway)
{service="api_gateway"}

# Lọc các dòng log có lỗi 401 hoặc 500 trên cả API và Gateway
{service=~"api_service|api_gateway"} |~ " 401 | 500 |ERROR"

# Đếm số dòng log lỗi mỗi phút theo từng service (biến Log thành Metric!)
sum by (service) (rate({service=~"api_service|api_gateway"} |= "401" [1m]))
```

---

### 5. Thực hành 3: Kiểm thử Cảnh báo (Prometheus → Alertmanager)

1. Mở http://localhost:9090/alerts để xem 3 quy tắc đang ở trạng thái **Inactive** (xanh).
2. Giả lập sự cố **API bị sập** bằng cách tắt container `api_service`:
   ```bash
   docker stop analytics_api
   ```
3. Đợi ~30–45 giây, reload http://localhost:9090/alerts:
   - `AnalyticsApiDown` chuyển từ **Inactive** → **Pending** (vàng) → **Firing** (đỏ).
4. Mở **Alertmanager** tại http://localhost:9093 → bạn sẽ thấy cảnh báo `AnalyticsApiDown` đã được gửi sang và gom nhóm sẵn sàng đẩy ra Slack/Telegram/Email.
5. Khôi phục lại API:
   ```bash
   docker start analytics_api
   ```
   Sau ~15–30 giây, cảnh báo sẽ tự động chuyển về trạng thái đã xử lý (Resolved).

---

### 6. Dọn dẹp sau khi thực hành

```bash
# Dừng toàn bộ cả App và Monitoring (giữ nguyên dữ liệu volume)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down

# Hoặc nếu chỉ muốn dừng riêng bộ Monitoring, giữ App chạy bình thường:
docker stop monitoring_prometheus monitoring_alertmanager monitoring_loki monitoring_promtail monitoring_grafana
```
