# SVC NOC-Center

Hệ thống **Network Operations Center (NOC)** đa chi nhánh (Multi-Site) hỗ trợ tự động khám phá sơ đồ mạng (**Topology Discovery**), gom cụm Switch/Hub không quản lý, giám sát thiết bị mạng qua **RouterOS API / SNMP**, giám sát đầu ghi & camera **CCTV/NVR (Hikvision ISAPI)** và truy cập **Web GUI nội bộ xuyên hầm VPN** không cần mở port (Port Forwarding).

---

## 1. Cấu trúc thư mục (Monorepo)

```text
SVC NOC Center/
├── docker-compose.yml                  # Orchestration: PostgreSQL 15, Redis 7, Backend, Celery, Frontend
├── README.md                           # Tài liệu cấu trúc & hướng dẫn sử dụng
├── backend/                            # Python 3.11 + FastAPI + SQLAlchemy (Async) + Celery
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── env.py                      # Cấu hình migration bất đồng bộ
│   ├── app/
│   │   ├── database.py                 # AsyncEngine & SessionLocal (PostgreSQL)
│   │   ├── models.py                   # Schema: Site, NetworkDevice, DevicePort, TopologyEdge, Alert
│   │   ├── main.py                     # FastAPI endpoints (Sites, Scan, Topology, CCTV, VPN Proxy)
│   │   ├── worker.py                   # Celery worker tasks
│   │   ├── collectors/                 # Các bộ thu thập dữ liệu phần cứng (Giai đoạn 2 & 5)
│   │   │   ├── mikrotik_collector.py   # RouterOS API (CPU/RAM, Traffic, ARP/DHCP, MNDP/LLDP)
│   │   │   ├── snmp_collector.py       # SNMPv2c MIBs (System, IF-MIB, Bridge FDB, Q-Bridge, LLDP)
│   │   │   ├── hikvision_isapi.py      # Hikvision ISAPI (HDD health, NVR Channels, Live Snapshot)
│   │   │   └── mac_vendor.py           # Tra cứu offline MAC OUI & tự động đoán loại thiết bị
│   │   └── services/                   # Xử lý nghiệp vụ & thuật toán (Giai đoạn 3 & 5)
│   │       ├── topology_builder.py     # Thuật toán nối dây Router -> Switch -> Hub ảo -> Endpoint
│   │       ├── alert_engine.py         # Phát hiện AP lạ (Tenda/TP-Link/Mercury), quá tải >50 MAC, đầy DHCP
│   │       └── vpn_proxy.py            # Reverse Proxy HTTP xuyên VPN vào thẳng Web GUI nội bộ
│   ├── scripts/
│   │   └── test_poller.py              # Công cụ CLI kiểm thử nhanh Router/Switch/MAC từ Terminal
│   └── tests/
│       └── test_api.py                 # Bộ kiểm thử tự động (Models, OUI, Collectors, Topology, ISAPI)
└── frontend/                           # Next.js 14 (App Router, TypeScript, Tailwind CSS, React Flow)
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/
        │   ├── page.tsx                # Trang chủ NOC Dashboard
        │   └── sites/[siteId]/
        │       ├── page.tsx            # Màn hình Sơ đồ mạng tương tác & Băng thông Multi-WAN
        │       └── cameras/
        │           └── page.tsx        # Màn hình Ma trận NVR/Camera, ổ cứng HDD & Live Thumbnail
        └── components/topology/        # Các Node tùy chỉnh trên sơ đồ React Flow + Dagre Layout
            ├── RouterNode.tsx          # Thẻ Router (CPU, RAM, Uptime, WAN/LAN Mbps)
            ├── SwitchNode.tsx          # Thẻ Switch kèm Ma trận đèn LED 24/48 cổng & cổng Uplink
            ├── UnmanagedGroupNode.tsx  # Khung nét đứt "Chưa xác định switch hoặc AP"
            ├── EndpointNode.tsx        # Thẻ Camera, NVR, Wi-Fi AP, PC
            ├── layout.ts               # Tự động dàn cây bằng Dagre + Truy vết đường truyền Uplink
            └── types.ts                # Kiểu dữ liệu TypeScript cho Topology
```

---

## 2. Danh sách Hãng & Thiết bị hỗ trợ

| Nhóm thiết bị | Hãng hỗ trợ | Giao thức thu thập |
|---|---|---|
| **Router / Firewall** | **MikroTik**, **Fortinet** (FortiGate), **DrayTek** (Vigor), **Cisco** | RouterOS API (`8728`), SNMPv2c + Enterprise OID |
| **Managed Switch** | **Ruijie / Reyee**, **Cisco**, **Aruba / HPE**, **Hikvision Switch**, **TP-Link** | SNMPv2c (`SNMPv2-MIB`, `IF-MIB`, `BRIDGE-MIB`, `Q-BRIDGE-MIB`, `LLDP-MIB`) |
| **Đầu ghi NVR & Camera** | **Hikvision**, **Dahua** (và các dòng tương thích chuẩn) | HTTP Digest Auth (`ISAPI`), phát hiện thụ động qua ARP/FDB + MAC OUI |
| **Wi-Fi AP & Endpoint** | **Ubiquiti**, **Aruba**, **Ruijie**, **TP-Link**, **Tenda**, **Mercury**, **Apple**, **Gigabyte**, **Intel**, **VMware**... | LLDP, ARP/DHCP Lease, nhận diện mã nhà sản xuất MAC OUI |

---

## 3. Hướng dẫn khởi chạy nhanh

### Cách 1: Chạy toàn bộ hệ thống bằng Docker Compose (Khuyên dùng)

Tại thư mục gốc `E:\SVC NOC Center`, chạy lệnh:

```powershell
docker compose up --build -d
```

Sau khi container khởi động xong:
- **Giao diện NOC Dashboard (Frontend)**: [http://localhost:3000](http://localhost:3000)
- **Tài liệu Swagger API (Backend)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL**: `localhost:5432` (User: `noc` / Pass: `noc_secret` / DB: `noc_center`)
- **Redis**: `localhost:6379`

---

### Cách 2: Chạy môi trường phát triển (Local Dev không cần Docker)

#### 1. Khởi chạy Backend (FastAPI)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Khởi chạy Frontend (Next.js)
```powershell
cd frontend
npm install
npm run dev
```

---

## 4. Hướng dẫn sử dụng các tính năng chính

### 4.1. Kiểm thử nhanh thiết bị qua CLI (`test_poller.py`)
Kiểm tra kết nối trực tiếp tới Router MikroTik, Switch SNMP và tra cứu MAC OUI ngay trên Terminal:

```powershell
# Chỉ tra cứu thử bảng MAC OUI
python backend/scripts/test_poller.py --mac BC:AD:28:11:22:33 00:1D:AA:11:22:33 18:64:72:AA:BB:CC

# Quét dữ liệu thật từ Router MikroTik và Managed Switch
python backend/scripts/test_poller.py --router-ip 10.10.0.1 --router-user admin --router-pass 123456 --switch-ip 10.10.0.2 --community public
```

### 4.2. Sử dụng Sơ đồ mạng tương tác (`/sites/[siteId]`)
1. Truy cập `http://localhost:3000/sites/1`.
2. Bấm nút **"Quét Sơ Đồ (Scan)"** ở góc phải trên để kích hoạt thuật toán bóc tách sơ đồ:
   - Tự động nối dây Uplink giữa **Router ➔ Core Switch ➔ Access Switch**.
   - Tự động gom các cổng Access có `>1 địa chỉ MAC` vào hộp nét đứt **"Chưa xác định switch hoặc AP"**.
3. **Truy vết đường truyền (Path Highlighting)**:
   - Rê chuột hoặc click vào bất kỳ Camera/Switch nào ở nhánh cuối: toàn bộ đường dây dẫn ngược về Router gốc sẽ sáng màu **Cyan**, các nhánh khác mờ đi, và **đúng lỗ cắm (Port LED)** trên từng Switch trung gian sẽ phát sáng.
4. Click vào thiết bị để mở ngăn chi tiết bên phải và bấm **"Mở Web GUI qua VPN"**.

### 4.3. Sử dụng Ma trận Camera & Đầu ghi NVR (`/sites/[siteId]/cameras`)
1. Bấm vào tab **"Camera"** trên thanh điều hướng (hoặc mở `http://localhost:3000/sites/1/cameras`).
2. **Khu vực đầu ghi NVR**: Theo dõi số kênh `Online/Tổng` và trạng thái từng ổ cứng (`OK` màu xanh, `ERROR` nhấp nháy đỏ).
3. **Bảng Camera LAN**: Xem từng Camera đang được ghi hình vào những đầu ghi NVR nào (kênh mấy) và cắm vào cổng Switch nào.
4. Click vào bất kỳ dòng Camera hoặc thẻ NVR nào để mở **Live ISAPI Snapshot Stream** ở khung bên phải.

---

## 5. Danh mục API Endpoints chính

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET / POST` | `/api/sites` | Danh sách & tạo mới chi nhánh (Site) |
| `GET / PUT / DELETE` | `/api/sites/{site_id}` | Chi tiết, cập nhật, xóa Site |
| `POST` | `/api/sites/{site_id}/scan` | Chạy Collector, giải thuật Topology + Cảnh báo và lưu vào DB |
| `GET` | `/api/topology/{site_id}` | Lấy dữ liệu Nodes/Edges/Alerts chuẩn React Flow |
| `GET` | `/api/sites/{site_id}/cctv` | Lấy ma trận đầu ghi NVR, ổ cứng HDD và danh sách Camera |
| `GET` | `/api/sites/{site_id}/nvrs/{nvr_ip}/channels/{ch}/snapshot` | Lấy ảnh chụp trực tiếp (JPEG/SVG) từ kênh NVR qua ISAPI |
| `GET / POST` | `/api/proxy/sites/{site_id}/{target_ip}/{subpath}` | Web GUI Reverse Proxy xuyên VPN vào thẳng IP nội bộ |

---

## 6. Chạy kiểm thử tự động (Unit Tests)

```powershell
python backend/tests/test_api.py
```
