# Kiểm thử PawRescue

Cập nhật 05/11/2026. Kết quả tự động cho phiên bản này:

- Django/PostgreSQL: **458 bài**, gồm **436 đạt** và **22 bỏ qua** thuộc chức năng nhận nuôi đã tắt.
- JavaScript/Node: **121/121 đạt**.
- Kịch bản gửi ca và tương tác ba vai trò: **4/4 đạt** trên schema PostgreSQL QA riêng.
- Django system check và kiểm tra migration còn thiếu: đạt.

Luồng chính được kiểm tra bằng ba phiên riêng, đăng nhập qua form và bật CSRF: client gửi ca → admin nhận thông báo và giao quản trị viên → client/admin chat hỗ trợ → admin/quản trị viên nhắn điều phối riêng → quản trị viên xác minh và báo hoàn thành → admin duyệt → ca thành công mới lên bản đồ. Client không đọc được tin điều phối; quản trị viên không tự duyệt kết quả cuối cùng.

Các nhóm kiểm thử khác bao gồm đăng ký/phân quyền, thông báo tự cập nhật, tải ảnh/tệp và quyền truy cập, bản đồ/tìm địa chỉ, biểu đồ, góp ý, quỹ/đóng góp, tổ chức và quản lý thành viên. Kết quả tự động không phải cam kết phần mềm không còn lỗi; chưa xác minh trực tiếp giao diện trên Firefox thật trong phiên công cụ này.

## Chạy lại

```bash
.venv/bin/python manage.py check --settings=config.test_settings
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv/bin/python manage.py test --settings=config.test_settings --noinput
node --test --test-isolation=none tests/*.test.cjs
```

Kiểm thử với PostgreSQL dùng schema tạm, tự xóa sau khi chạy:

```bash
.venv/bin/python scripts/run_postgres_audit.py
```

Cần PostgreSQL đang chạy và tài khoản cấu hình trong `.env` được tạo schema QA. Công cụ chỉ tìm bảng trong schema QA, không chạy kiểm thử trên bảng dữ liệu thật. Tệp tải lên dùng thư mục tạm; API key Geoapify thật được tắt trong bộ kiểm thử.

File `.env`, CSDL, tệp người dùng và thư mục `output/` không nằm trong bản mã nguồn GitHub. Bộ tài khoản thử và hồ sơ mẫu trên máy phát triển không tự xuất hiện khi clone repo sang máy khác. Không ghi mật khẩu tài khoản thật vào mã nguồn hoặc báo cáo công khai.
