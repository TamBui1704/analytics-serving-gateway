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
   curl -H "X-API-Key: demo-key-123" "http://localhost:8000/api/v1/sales/daily?days=7"
   ```

---

# 🚪 NẤC 2: API Gateway (NGINX Thuần)

### 1. Mục tiêu nấc này:
- Hiểu tại sao **không nên** để client gọi thẳng vào backend.
- Hiểu vai trò của **Edge Authentication**: Chặn request sai ngay tại cổng vào, không tốn tài nguyên của server backend.
- Hiểu vai trò của **Rate Limiting**: Chống spam và bảo vệ hệ thống khỏi bị quá tải.

### 2. Khởi động Nấc 2:
Bật thêm container `api_gateway`:
```bash
docker compose up -d api_gateway
```

Lúc này kiến trúc trở thành:
```
Client ──► Cổng 8080 (NGINX Gateway) ──► Cổng 8000 (FastAPI) ──► ClickHouse (8123)
```

### 3. Thực hành kiểm chứng các tính năng của Gateway:

#### Thí nghiệm 2.1: Gọi bình thường qua Gateway (Thành công)
Gọi qua cổng **8080** thay vì 8000:
```bash
curl -H "X-API-Key: demo-key-123" "http://localhost:8080/api/v1/sales/daily?days=7"
```
👉 Bạn vẫn nhận được dữ liệu, nhưng request đã đi qua NGINX trung gian.

#### Thí nghiệm 2.2: Test Edge Authentication (Chặn đứng tại cổng)
Thử gửi request mà **KHÔNG** truyền header `X-API-Key`:
```bash
curl -i http://localhost:8080/api/v1/sales/daily
```
👉 **Hiện tượng**: NGINX lập tức trả về:
```json
HTTP/1.1 401 Unauthorized
{"error": "Unauthorized", "message": "API Gateway: Missing X-API-Key header"}
```
*(Hãy kiểm tra logs của FastAPI bằng `docker logs analytics_api`, bạn sẽ thấy **hoàn toàn không có log nào**, chứng minh request đã bị chặn ngay ở vòng gửi xe!)*

#### Thí nghiệm 2.3: Test Rate Limiting (Chặn spam)
Trong file [`gateway/nginx.conf`](gateway/nginx.conf), chúng ta quy định tối đa **5 requests/giây**. Hãy chạy vòng lặp gửi dồn dập 15 requests trong 1 giây:
```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "Req $i: HTTP %{http_code}\n" \
    -H "X-API-Key: demo-key-123" \
    http://localhost:8080/api/v1/sales/daily
done
```
👉 **Hiện tượng**: 
- Các request đầu: `HTTP 200`
- Các request dồn dập tiếp theo: `HTTP 429 Too Many Requests`!

---

# 🌐 NẤC 2.5: Subdomain Routing + Phân Quyền Key Theo Dịch Vụ

> Đây là bài thực hành mở rộng sau khi bạn đã nắm vững Nấc 2.
> Mục tiêu: Trải nghiệm mô hình Gateway thực tế ở các dự án Production —
> **1 Gateway phục vụ nhiều dịch vụ, mỗi khách hàng chỉ vào được dịch vụ họ được cấp quyền**.

---

### 1. Mục tiêu bài thực hành này

- Hiểu cách NGINX phân luồng request theo **Subdomain** (tên miền phụ).
- Hiểu cách **phân quyền API Key** theo từng dịch vụ bằng directive `map`.
- Hiểu tại sao các dự án Production **không chia key riêng cho từng dịch vụ**, mà cấp cho mỗi khách **1 Master Key duy nhất** rồi để Gateway lo phân quyền.

---

### 2. Kiến trúc bài thực hành

```
                        ┌─────────────────────────────────────┐
                        │       SERVER NGINX GATEWAY :8080    │
                        │                                     │
Client gọi vào ────────►│  analytics.local ──► FastAPI :8000  │
  kèm X-Client-Key      │  branding.local  ──► Trả JSON giả  │
                        │                                     │
                        │  Ma trận phân quyền (nginx.conf):   │
                        │  key_user_a   → Chỉ analytics       │
                        │  key_user_b   → Chỉ branding        │
                        │  key_user_vip → Cả hai dịch vụ      │
                        └─────────────────────────────────────┘
```

**Bảng phân quyền khách hàng:**

| Client Key | Quyền vào `analytics.local` | Quyền vào `branding.local` |
|:---:|:---:|:---:|
| `key_user_a` | ✅ Có | ❌ Không |
| `key_user_b` | ❌ Không | ✅ Có |
| `key_user_vip` | ✅ Có | ✅ Có |

---

### 3. Giải thích file cấu hình hiện tại [`gateway/nginx.conf`](gateway/nginx.conf)

Cơ chế phân quyền dùng directive `map` — hoạt động như một bảng tra cứu `switch/case`:

```nginx
# NGINX đọc giá trị header X-Client-Key do client gửi lên,
# rồi dùng nó làm "chìa khóa" tra vào bảng để sinh ra biến mới.
map $http_x_client_key $allow_analytics {
    default        0;         # Không có trong danh sách → bị từ chối
    "key_user_a"   1;         # key_user_a → được phép
    "key_user_vip" 1;         # key_user_vip → được phép
}
```

Tại mỗi `location`, NGINX chỉ kiểm tra biến vừa tạo ra:
```nginx
if ($allow_analytics = 0) {
    return 403 '{"error": "Forbidden: You do not have access to Analytics service"}\n';
}
```

**Điểm bảo mật quan trọng:** Khách hàng chỉ biết `X-Client-Key` của họ. NGINX âm thầm **tự thêm** key nội bộ `X-API-Key: demo-key-123` trước khi chuyển vào FastAPI. FastAPI không bao giờ bị lộ key ra ngoài!

---

### 4. Thiết lập môi trường test

Vì chúng ta không mua tên miền thật, ta dùng file `/etc/hosts` để "đánh lừa" máy tính:
khi trình duyệt/curl gõ `analytics.local`, máy sẽ trỏ về chính `127.0.0.1` (máy mình).

#### Bước 4.1 — Thêm tên miền giả vào `/etc/hosts`

```bash
echo "127.0.0.1 analytics.local branding.local" | sudo tee -a /etc/hosts
```

Kiểm tra lại (phải thấy dòng vừa thêm ở cuối):
```bash
tail -3 /etc/hosts
# 127.0.0.1 analytics.local branding.local
```

> **Giải thích:** File `/etc/hosts` là "cuốn danh bạ nội bộ" của máy tính.
> Máy tính luôn tra file này TRƯỚC khi hỏi DNS thật trên Internet.
> Vì vậy không cần mua domain, bạn vẫn có thể dùng tên miền tùy ý trên máy.

#### Bước 4.2 — Khởi động toàn bộ stack (nếu chưa chạy)

```bash
docker compose up -d
```

---

### 5. Thực hành bằng Terminal (curl)

Cú pháp chung:
```bash
curl -s -H "X-Client-Key: <key_của_bạn>" "http://<subdomain>:8080/<endpoint>"
```

#### Thí nghiệm 2.5.1 — Khách A (chỉ có quyền Analytics)

```bash
# ✅ THÀNH CÔNG: key_user_a được phép vào Analytics
curl -H "X-Client-Key: key_user_a" "http://analytics.local:8080/api/v1/sales/daily?days=7"

# ❌ BỊ CHẶN 403: key_user_a không có quyền vào Branding
curl -H "X-Client-Key: key_user_a" "http://branding.local:8080/"
```

Kết quả mong đợi:
```
# Lần 1: Dữ liệu JSON từ ClickHouse (hoặc [] nếu chưa có dữ liệu)
# Lần 2: {"error": "Forbidden: You do not have access to Branding service"}
```

#### Thí nghiệm 2.5.2 — Khách B (chỉ có quyền Branding)

```bash
# ❌ BỊ CHẶN 403: key_user_b không có quyền vào Analytics
curl -H "X-Client-Key: key_user_b" "http://analytics.local:8080/api/v1/sales/daily?days=7"

# ✅ THÀNH CÔNG: key_user_b được phép vào Branding
curl -H "X-Client-Key: key_user_b" "http://branding.local:8080/"
```

Kết quả mong đợi:
```
# Lần 1: {"error": "Forbidden: You do not have access to Analytics service"}
# Lần 2: {"service": "Branding API", "status": "active", "message": "Welcome to Branding Hub!"}
```

#### Thí nghiệm 2.5.3 — Khách VIP (có quyền tất cả dịch vụ)

```bash
# ✅ THÀNH CÔNG trên cả hai dịch vụ
curl -H "X-Client-Key: key_user_vip" "http://analytics.local:8080/api/v1/sales/daily?days=7"
curl -H "X-Client-Key: key_user_vip" "http://branding.local:8080/"
```

#### Thí nghiệm 2.5.4 — Kẻ xấu dùng key giả

```bash
# ❌ BỊ CHẶN 403 trên tất cả dịch vụ — không vào được đâu cả
curl -H "X-Client-Key: hacker_fake_key_123" "http://analytics.local:8080/api/v1/sales/daily"
curl -H "X-Client-Key: hacker_fake_key_123" "http://branding.local:8080/"
```

---

### 6. Thực hành bằng Postman (GUI)

#### Bước 6.1 — Cài đặt Request trong Postman

1. Mở Postman → Tạo Request mới → Chọn method `GET`.
2. Nhập URL: `http://analytics.local:8080/api/v1/sales/daily?days=7`
3. Chuyển sang tab **Headers**, thêm:

   | Key | Value |
   |---|---|
   | `X-Client-Key` | `key_user_a` |

4. Bấm **Send**.

#### Bước 6.2 — Tạo Collection để test nhanh các kịch bản

Tạo 1 Postman Collection tên **"Analytics Gateway - Subdomain Test"**, bên trong tạo các request:

| Tên Request | URL | Header `X-Client-Key` | Kết quả kỳ vọng |
|---|---|---|---|
| Khách A → Analytics | `http://analytics.local:8080/api/v1/sales/daily` | `key_user_a` | `200 OK` |
| Khách A → Branding | `http://branding.local:8080/` | `key_user_a` | `403 Forbidden` |
| Khách B → Analytics | `http://analytics.local:8080/api/v1/sales/daily` | `key_user_b` | `403 Forbidden` |
| Khách B → Branding | `http://branding.local:8080/` | `key_user_b` | `200 OK` |
| VIP → Analytics | `http://analytics.local:8080/api/v1/sales/daily` | `key_user_vip` | `200 OK` |
| VIP → Branding | `http://branding.local:8080/` | `key_user_vip` | `200 OK` |
| Key giả → Anywhere | `http://analytics.local:8080/api/v1/sales/daily` | `hacker_key` | `403 Forbidden` |

---

### 7. Cách thêm / thu hồi quyền một khách hàng

Toàn bộ việc quản lý quyền nằm trong file [`gateway/nginx.conf`](gateway/nginx.conf) phần `map`.

#### Thêm khách hàng mới (Công ty C, chỉ có quyền Analytics):
```nginx
map $http_x_client_key $allow_analytics {
    default              0;
    "key_user_a"         1;
    "key_user_vip"       1;
    "key_company_c_xyz"  1;   # ← Thêm dòng này
}
```

#### Thu hồi quyền khi key bị lộ (Khách A làm lộ key lên GitHub):
```nginx
map $http_x_client_key $allow_analytics {
    default              0;
    # "key_user_a"       1;   # ← Comment lại hoặc xóa dòng này (vô hiệu hóa ngay)
    "key_user_a_v2"      1;   # ← Cấp key mới cho Khách A
    "key_user_vip"       1;
}
```

Sau khi sửa file, **reload NGINX ngay lập tức** (không cần tắt container):
```bash
docker exec analytics_gateway nginx -s reload
```

> **Lưu ý:** Chỉ cần reload NGINX — các container FastAPI và ClickHouse vẫn chạy bình thường,
> không có downtime, không ảnh hưởng đến các khách hàng khác đang gọi API.

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
│    - Kiểm tra header X-API-Key, chặn spam (Rate Limit)     │
│    - Chuyển tiếp request vào Service                        │
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

# 3. Tạo Secret lưu mật khẩu và API Keys
# Cách tốt nhất (Bảo mật): Tạo trực tiếp bằng lệnh CLI, tránh lưu key vào file để không sợ lộ lên Git:
kubectl create secret generic analytics-gateway-secret \
  --from-literal=API_KEYS="demo-key-123,demo-key-456" \
  --from-literal=CLICKHOUSE_HOST="localhost" \
  --from-literal=CLICKHOUSE_PASSWORD="" \
  -n analytics \
  --dry-run=client -o yaml | kubectl apply -f -
# (Hoặc nếu dùng file: copy k8s/secret.yaml.example thành k8s/secret.yaml - file này đã được .gitignore)

# 4. Tạo Deployment (Khởi chạy 2 Pod FastAPI)
kubectl apply -f k8s/api-deployment.yaml

# 5. Tạo Service (Bộ cân bằng tải nội bộ)
kubectl apply -f k8s/api-service.yaml

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
3. Gọi API qua Ingress Gateway:
   ```bash
   curl -H "X-API-Key: demo-key-123" "http://analytics.local/api/v1/sales/daily?days=7"
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
