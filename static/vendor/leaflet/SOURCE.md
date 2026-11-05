# Leaflet 1.9.4

Tệp thư viện gốc được lưu cùng website để việc khởi tạo bản đồ không phải chờ CDN bên ngoài. Bản đồ nền vẫn cần kết nối đến nhà cung cấp ô bản đồ.

- Phiên bản cố định: **1.9.4**.
- Tài liệu tải chính thức: [Leaflet Downloads](https://leafletjs.com/download.html)
- Gói nguồn đã tải: [Leaflet 1.9.4 từ npm](https://registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz)
- Giấy phép BSD-2-Clause được giữ nguyên trong `LICENSE`.
- `leaflet.js`, `leaflet.css`, `leaflet.js.map` và thư mục `images/` được chép nguyên byte từ gói phát hành; không sửa mã thư viện.

Hai mã kiểm tra SHA-256 dạng Base64 bên dưới đã được đối chiếu với trang tải chính thức:

| Tệp | SHA-256 Base64 |
| --- | --- |
| `leaflet.js` | `20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=` |
| `leaflet.css` | `p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=` |

Thư mục `images/` gồm `layers.png`, `layers-2x.png`, `marker-icon.png`, `marker-icon-2x.png` và `marker-shadow.png`. Giữ các tệp ảnh bên cạnh CSS theo đúng cấu trúc thư viện. Tệp `leaflet.js.map` phục vụ xem mã khi gỡ lỗi và được giữ để liên kết cuối tệp JavaScript hoạt động.
