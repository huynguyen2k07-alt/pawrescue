# Các phần chính để trình bày đồ án PawRescue

Luồng chính: **Người dùng báo ca → admin xác nhận và nhắn tin → chuyển đơn vị cứu hộ → admin đánh giá và chốt hồ sơ.** Có thể giao người phụ trách trong hệ thống khi cần.

## Code nên mở khi trình bày

| Phần | Vị trí | Ý cần giải thích |
| --- | --- | --- |
| Gửi báo ca | `rescue/forms.py`, `rescue/views.py` → `case_create` | Kiểm tra dữ liệu, gắn người báo tin, lưu ảnh và gửi thông báo cho admin. |
| Vị trí bản đồ | `static/js/maps.js`, `rescue/geography.py` | Đồng bộ ghim với tọa độ; yêu cầu địa chỉ cụ thể và vị trí trong phạm vi Đà Nẵng. |
| Phân quyền và riêng tư | `rescue/permissions.py`, `rescue/views.py` → `case_detail` | Admin, người báo tin và người được phân công có phạm vi truy cập khác nhau; bảo vệ liên hệ và vị trí chính xác. |
| Phân công | `rescue/views.py` → `case_assign`, `case_unassign` | Chỉ admin giao/thu hồi việc; thu hồi quyền nhưng giữ lịch sử xử lý. |
| Chuyển bên thứ ba | `rescue/forms.py` → `CaseHandoffForm`, `rescue/views.py` → `case_handoff` | Chọn đơn vị đã xác minh, lưu lịch sử bàn giao và giữ quyền đánh giá cuối cùng ở quản trị viên. |
| Trao đổi riêng | `rescue/views.py` → `case_messages` | Tin điều phối chỉ cho người gửi/người nhận có quyền trong ca. |
| Cập nhật và chốt ca | `rescue/views.py` → `case_add_update`, `case_update_status` | Người xử lý cập nhật hiện trường; admin đánh giá, ghi thời điểm chốt và khóa ca đã kết thúc. |
| Lịch sử dữ liệu | `rescue/models.py` | Các model chính: `RescueCase`, `RescueAssignment`, `RescueUpdate`, `RescueCaseMessage`, `CaseStatusHistory`. |

## Trình tự demo

1. Tài khoản người dùng gửi một báo ca mới, nhập địa chỉ và ghim vị trí.
2. Admin mở yêu cầu, xác nhận và nhắn người báo tin từ hồ sơ.
3. Chuyển yêu cầu cho đơn vị cứu hộ, hoặc giao người phụ trách trong hệ thống.
4. Admin nhập đánh giá và chốt kết quả cứu hộ.
5. Người báo tin xem kết quả; mở lại hồ sơ để chỉ ra lịch sử phân công và trạng thái.

Khi giải thích quyền, lưu ý `is_staff` chỉ là điều kiện vào giao diện quản trị theo quyền Django được cấp. Admin điều phối cứu hộ phải là tài khoản đang hoạt động có `is_superuser`.

Đơn vị bên ngoài được thêm ở mục **Đơn vị tiếp nhận**, có số điện thoại hoặc email, đã xác minh và đang nhận ca. Đơn vị không cần tạo tài khoản để được ghi nhận bàn giao. Nút **Soạn email bàn giao** mở bản nháp để quản trị viên xem và tự gửi; có thể gọi theo số liên hệ để xác nhận tiếp nhận.

Trang quản trị có 4 mục chính: yêu cầu, hộp thư, tài khoản/nhân sự và đơn vị tiếp nhận. Mở yêu cầu để xử lý; **Sửa thông tin** chỉ dùng khi cần chỉnh nội dung. Biểu mẫu chỉ giữ một nút **Lưu thay đổi**. Các liên kết hỗ trợ chuột giữa và Ctrl+bấm để mở tab mới.

Trang chính tập trung vào gửi yêu cầu, xem bản đồ và theo dõi trạng thái. Các khu vực giới thiệu đội ngũ, bài kiến thức và góp ý không còn xuất hiện trên trang chính. Xóa bài dùng trang xác nhận riêng; hoàn tất ca vẫn giữ lại hồ sơ và lịch sử để đối chiếu.

Các chú thích trong code được giữ ở những điểm nghiệp vụ trên. Phần cú pháp đơn giản, CSS, kiểm thử và migration đã bỏ chú thích từng dòng.

Xem [danh sách chú thích và tác dụng](DANH_SACH_CHU_THICH.md) để mở đúng từng vị trí trong code.
