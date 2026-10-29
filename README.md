# PawRescue · Báo tin và điều phối cứu hộ

Website Django cho phép người dùng báo ca động vật cần cứu hộ tại Đà Nẵng. Admin tiếp nhận, phân công người xử lý, trao đổi riêng và đánh giá kết quả trước khi chốt hồ sơ. Bản đồ giúp xác định vị trí của ca. Tính năng nhận nuôi hiện đã tắt.

## Chạy server trên máy hiện tại

Mở terminal trong thư mục dự án rồi chạy:

```bash
cd /home/huy/animal-rescue
source .venv/bin/activate
python manage.py runserver
```

Giữ terminal mở khi dùng website. Truy cập [trang chủ](http://127.0.0.1:8000/), [báo ca mới](http://127.0.0.1:8000/cases/new/) hoặc [admin](http://localhost:8000/admin/). Nhấn `Ctrl+C` trong terminal để dừng server.

Nếu báo cổng 8000 đang được dùng, server có thể đã chạy ở terminal khác. Có thể chạy thêm một server bằng `python manage.py runserver 8001` rồi truy cập cổng 8001.

## Cài lại môi trường khi cần

Dự án dùng Python, PostgreSQL và các thư viện được ghim phiên bản trong `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

PostgreSQL phải đang chạy. File `.env` ở thư mục gốc cung cấp `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` và các thiết lập tùy chọn khác. Máy hiện tại đã có file này; không cần ghi lại mật khẩu vào mã nguồn. Chế độ phát triển tại máy cá nhân dùng `DJANGO_DEBUG=true`.

Muốn tạo tài khoản admin mới trên một môi trường mới, dùng `python manage.py createsuperuser`. Tài khoản đăng ký qua website là tài khoản người dùng thông thường.

## Đọc và sửa code

Chú thích trong code chỉ tập trung vào nghiệp vụ chính. Xem [các phần cần trình bày đồ án](docs/HUONG_DAN_DOC_CODE.md) để theo dõi luồng báo ca, bản đồ, phân quyền, phân công và admin chốt kết quả.

[Danh sách chú thích](docs/DANH_SACH_CHU_THICH.md) liệt kê từng vị trí đã ghi chú, tên hàm và tác dụng của đoạn code để tra cứu khi trình bày.

Các file trong `.venv/` là thư viện cài đặt; `media/` và `private_media/` chứa tệp người dùng tải lên; `output/` chứa kết quả kiểm thử. Đây không phải nơi sửa chức năng của website.

## Kiểm tra sau khi sửa

```bash
# Kiểm tra cấu hình Django.
.venv/bin/python manage.py check --settings=config.test_settings

# Chạy bộ kiểm thử Python trong SQLite tách biệt dữ liệu thật.
.venv/bin/python manage.py test --settings=config.test_settings --noinput

# Kiểm tra tương tác bản đồ và hỗ trợ trực tuyến.
node tests/maps.test.cjs
node --test --test-isolation=none tests/support.test.cjs
```

Muốn kiểm thử với PostgreSQL đang cấu hình, chạy `.venv/bin/python scripts/run_postgres_audit.py`. Script tạo schema kiểm thử riêng, chạy migration và kiểm thử trong schema đó rồi xóa schema khi kết thúc. Nó cần quyền tạo schema trong database.

Báo cáo kiểm tra admin và các chức năng trước đợt chú thích nằm tại [output/admin-audit-2026-10-27/REPORT.md](output/admin-audit-2026-10-27/REPORT.md).
