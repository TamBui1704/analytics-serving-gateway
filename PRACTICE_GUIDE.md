# 🎓 Giáo Trình Thực Hành 3 Nấc: Từ Docker đến API Gateway & K8s

Dự án này được thiết kế để bạn học từ gốc rễ đến nâng cao theo **3 Nấc thang**. Bạn sẽ không bị ngợp vì mỗi nấc giải quyết một bài toán duy nhất.

---

## 🎯 BẢN ĐỒ 3 NẤC HỌC TẬP

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
Trong file [`gateway/nginx.conf`](gateway/nginx.conf), chúng ta quy định tối đa **10 requests/giây**. Hãy chạy vòng lặp gửi dồn dập 25 requests:
```bash
NOW=$(date +%s)
TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

for i in {1..25}; do
  curl -s -o /dev/null -w "Req $i: HTTP %{http_code}\n" \
    -H "Timestamp: ${NOW}" \
    -H "Authorization: Bearer ${TOKEN}" \
    http://localhost:8080/api/v1/sales/daily
done
```
👉 **Hiện tượng**: 
- Các request đầu: `HTTP 200`
- Các request dồn dập vượt quá ngưỡng giới hạn: `HTTP 503` hoặc `HTTP 429` do NGINX Rate Limiting chặn đứng!

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
minikube start --driver=docker

# Bật NGINX Ingress Controller (để dùng k8s/ingress.yaml)
minikube addons enable ingress

# Bật Metrics Server (để HPA đo được % CPU)
minikube addons enable metrics-server
```

#### Bước 2.3: Nạp image FastAPI vào Minikube
Vì image `analytics-api:v1` đang nằm ở Docker máy thật, ta nạp thẳng vào Minikube mà không cần đẩy lên mạng:
```bash
# 1. Build image từ code hiện tại (nếu chưa build)
docker build -t analytics-api:v1 .

# 2. Đưa image vào trong cụm Minikube
minikube image load analytics-api:v1
```

*(Lưu ý nhỏ: Trong file `k8s/api-deployment.yaml`, bạn sửa dòng `image:` thành `analytics-api:v1` và `imagePullPolicy: IfNotPresent` để K8s dùng ngay image vừa nạp).*

---

### 3. Các bước triển khai (Deploy) toàn bộ dự án lên K8s

Thực hiện áp dụng các file YAML theo đúng thứ tự:

```bash
# 1. Tạo "khu vực riêng" (Namespace) cho dự án
kubectl apply -f k8s/namespace.yaml

# 2. Tạo ConfigMap lưu cấu hình không nhạy cảm (Port, DB name, Workers...)
kubectl apply -f k8s/configmap.yaml -n analytics

# 3. Tạo Secret lưu mật khẩu và API Keys cho từng service
# Cách tốt nhất (Bảo mật): Tạo trực tiếp bằng lệnh CLI, tránh lưu key vào file để không sợ lộ lên Git:
kubectl create secret generic analytics-gateway-secret \
  --from-literal=ANALYTICS_API_KEYS="key_user_a,key_user_vip,demo-key-123" \
  --from-literal=BRANDING_API_KEYS="key_user_b,key_user_vip" \
  --from-literal=CLICKHOUSE_HOST="localhost" \
  --from-literal=CLICKHOUSE_PASSWORD="" \
  -n analytics \
  --dry-run=client -o yaml | kubectl apply -f -
# (Hoặc nếu dùng file: copy k8s/secret.yaml.example thành k8s/secret.yaml - file này đã được .gitignore)

# 4. Tạo Deployment (Khởi chạy 2 Pod FastAPI)
kubectl apply -f k8s/api-deployment.yaml

# 5. Tạo Service (Bộ cân bằng tải nội bộ)
kubectl apply -f k8s/api-service.yaml

# 5.5 Tạo Secret TLS chứa chứng chỉ SSL cho HTTPS (BẮT BUỘC trước khi tạo Ingress):
# Lệnh này đọc 2 file cert và key từ máy tính nạp vào etcd của K8s.
# Dù Pod NGINX có chết hay restart bao nhiêu lần, Secret trong etcd vẫn giữ nguyên 100%!
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
1. Lấy địa chỉ IP của cụm Minikube:
   ```bash
   minikube ip
   ```
2. Thêm IP đó vào `/etc/hosts` cho tên miền `analytics.local`:
   ```bash
   echo "$(minikube ip) analytics.local" | sudo tee -a /etc/hosts
   ```
3. Gọi API qua Ingress Gateway (với chữ ký SHA-256 + Timestamp):
   ```bash
   NOW=$(date +%s)
   TOKEN=$(echo -n "demo-key-123${NOW}" | sha256sum | awk '{print $1}')

   curl -H "Timestamp: ${NOW}" \
        -H "Authorization: Bearer ${TOKEN}" \
        "http://analytics.local/api/v1/sales/daily?days=7"
   ```
   *(Request đi qua: Ingress NGINX ──► Service ──► chia tải ngẫu nhiên vào 1 trong 2 Pod FastAPI!)*

---

### 6. Dọn dẹp sau khi thực hành K8s

Khi thực hành xong, muốn giải phóng RAM/CPU của máy tính:
```bash
# Xóa toàn bộ tài nguyên của dự án
kubectl delete namespace analytics

# Dừng cụm Minikube
minikube stop
```
