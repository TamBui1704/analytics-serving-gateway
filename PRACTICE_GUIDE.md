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

# ☸️ NẤC 3: Kubernetes (K8s) & GitHub Actions (CI/CD)

Khi bạn đã hiểu bản chất ở Nấc 1 & Nấc 2, bạn sẽ thấy Nấc 3 thực chất là **chuyển đổi các khái niệm trên sang nền tảng K8s để có khả năng tự động hóa và chịu tải cao**:

| Nấc 2 (Docker thuần) | Nấc 3 (Kubernetes) | Vai trò |
|----------------------|-------------------|---------|
| `api_gateway (NGINX)` | **NGINX Ingress** (`k8s/ingress.yaml`) | Cổng API Gateway, Rate Limit, Edge Auth |
| `docker-compose.yml` | **K8s Service** (`k8s/api-service.yaml`) | Cân bằng tải nội bộ |
| `api_service (1 container)` | **K8s Deployment** (`k8s/api-deployment.yaml`) | Chạy nhiều Pods song song, tự phục hồi khi crash |
| Không có | **HPA** (`k8s/hpa.yaml`) | Tự động tăng Pods khi CPU cao |
| Chạy `docker build` bằng tay | **GitHub Actions** (`.github/workflows/ci-cd.yml`) | Tự động test, build image và deploy khi push code |

*(Chi tiết thực hành Nấc 3 sẽ được hướng dẫn khi bạn đã thành thạo Nấc 1 và Nấc 2!)*
