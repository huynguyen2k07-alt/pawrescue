# Danh sách chú thích trong dự án PawRescue

Bấm vào vị trí để mở đúng dòng code. Các giải thích dùng tiếng Việt; tên hàm, biến và chỉ thị kỹ thuật được giữ nguyên.

## 1. Các ghi chú quan trọng để trình bày đồ án

Có **33 ghi chú ngắn**, tập trung vào báo tin, bản đồ, phân quyền, bàn giao và xử lý của quản trị viên.

| STT | Vị trí và hàm/khu vực | Tác dụng |
| --- | --- | --- |
| 1 | [accounts/admin.py:63](/home/huy/animal-rescue/accounts/admin.py:63) — `UserAdmin.get_readonly_fields` | Bảo vệ quyền quản trị tài khoản. |
| 2 | [config/admin_site.py:20](/home/huy/animal-rescue/config/admin_site.py:20) — `RescueAdminSite.get_app_list` | Thu gọn menu về chức năng chính và giữ việc kiểm tra quyền của từng chức năng. |
| 3 | [donations/services.py:17](/home/huy/animal-rescue/donations/services.py:17) — `save_reviewed_donation` | Dùng chung quy tắc duyệt đóng góp giữa các giao diện. |
| 4 | [rescue/forms.py:115](/home/huy/animal-rescue/rescue/forms.py:115) — `RescueCaseForm.clean` | Kiểm tra vị trí trước khi lưu báo cáo. |
| 5 | [rescue/forms.py:158](/home/huy/animal-rescue/rescue/forms.py:158) — `CaseStatusUpdateForm.clean` | Bảo đảm quyết định cuối cùng có nội dung đánh giá. |
| 6 | [rescue/models.py:105](/home/huy/animal-rescue/rescue/models.py:105) — `RescueCase.change_status` | Tránh lưu trạng thái mà thiếu thời điểm chốt hoặc lịch sử tương ứng. |
| 7 | [rescue/permissions.py:11](/home/huy/animal-rescue/rescue/permissions.py:11) — `is_rescue_admin` | Xác định người có quyền điều hành và quyết định kết quả ca. |
| 8 | [rescue/permissions.py:22](/home/huy/animal-rescue/rescue/permissions.py:22) — `visible_cases_for` | Giữ riêng tin báo chưa được tiếp nhận cho những người liên quan. |
| 9 | [rescue/permissions.py:35](/home/huy/animal-rescue/rescue/permissions.py:35) — `eligible_assignees` | Lọc danh sách người đủ điều kiện nhận nhiệm vụ cứu hộ. |
| 10 | [rescue/storage.py:29](/home/huy/animal-rescue/rescue/storage.py:29) — `PrivateRescueStorage.url` | Bắt buộc kiểm tra quyền khi tải ảnh hiện trường. |
| 11 | [rescue/uploads.py:176](/home/huy/animal-rescue/rescue/uploads.py:176) — `sanitize_image_upload` | Kiểm tra tệp tải lên và hạn chế lộ thông tin được nhúng trong ảnh. |
| 12 | [rescue/views.py:108](/home/huy/animal-rescue/rescue/views.py:108) — `_display_coordinates` | Bảo vệ vị trí nhạy cảm khi hiển thị bản đồ. |
| 13 | [rescue/views.py:143](/home/huy/animal-rescue/rescue/views.py:143) — `case_image` | Ngăn tải ảnh của ca bằng đường dẫn khi không có quyền xem ca. |
| 14 | [rescue/views.py:542](/home/huy/animal-rescue/rescue/views.py:542) — `case_create` | Lưu hồ sơ đầy đủ và báo cho quản trị viên kiểm tra yêu cầu mới. |
| 15 | [rescue/views.py:662](/home/huy/animal-rescue/rescue/views.py:662) — `case_add_update` | Giới hạn người được thêm cập nhật hiện trường. |
| 16 | [rescue/views.py:769](/home/huy/animal-rescue/rescue/views.py:769) — `case_handoff` | Lưu bàn giao đơn vị, kết thúc phân công cũ và giữ quyền chốt kết quả ở quản trị viên. |
| 17 | [rescue/views.py:827](/home/huy/animal-rescue/rescue/views.py:827) — `case_update_status` | Giữ quyền đánh giá cuối cùng và khóa hồ sơ đã kết thúc. |
| 18 | [rescue/views.py:868](/home/huy/animal-rescue/rescue/views.py:868) — `case_assign` | Điều phối nhiệm vụ và bảo vệ nội dung chỉ dẫn. |
| 19 | [rescue/views.py:937](/home/huy/animal-rescue/rescue/views.py:937) — `case_messages` | Giới hạn tin riêng theo đúng người gửi và người nhận. |
| 20 | [rescue/views.py:993](/home/huy/animal-rescue/rescue/views.py:993) — `case_unassign` | Ngừng quyền hiện tại mà vẫn giữ hồ sơ để đối chiếu. |
| 21 | [support/views.py:35](/home/huy/animal-rescue/support/views.py:35) — `_operator_ids` | Giữ riêng thông báo của hội thoại đã được phân công. |
| 22 | [support/views.py:123](/home/huy/animal-rescue/support/views.py:123) — `_lock_operator_conversation` | Ngăn xử lý nhầm khi nhiều người cùng thao tác hoặc đổi phân công. |
| 23 | [static/js/maps.js:15](/home/huy/animal-rescue/static/js/maps.js:15) — `isWithinDaNang` | Giới hạn vị trí người dùng chọn theo khu vực tiếp nhận. |
| 24 | [static/js/maps.js:41](/home/huy/animal-rescue/static/js/maps.js:41) — `getTileProviders` | Ưu tiên lớp bản đồ mặc định không phụ thuộc khóa dịch vụ. |
| 25 | [static/js/maps.js:211](/home/huy/animal-rescue/static/js/maps.js:211) — `setLocation` | Bảo đảm vị trí nhìn thấy trên bản đồ khớp dữ liệu gửi lên. |
| 26 | [static/js/maps.js:300](/home/huy/animal-rescue/static/js/maps.js:300) — `initDetailMap` | Hiển thị đúng vị trí gần đúng do máy chủ cung cấp. |
| 27 | [static/js/maps.js:332](/home/huy/animal-rescue/static/js/maps.js:332) — `buildPopup` | Ngăn nội dung nhập vào bị thực thi như mã trên cửa sổ thông tin bản đồ. |
| 28 | [static/js/support-chat.js:105](/home/huy/animal-rescue/static/js/support-chat.js:105) — `renderMessages` | Cập nhật khung hỗ trợ khi một tin cũ được sửa hoặc thay đổi tệp. |
| 29 | [static/admin/js/support-inbox.js:142](/home/huy/animal-rescue/static/admin/js/support-inbox.js:142) — `refreshInbox` | Cập nhật quyền truy cập và nút thao tác khi hội thoại thay đổi. |
| 30 | [templates/rescue/case_form.html:18](/home/huy/animal-rescue/templates/rescue/case_form.html:18) — `Biểu mẫu báo ca` | Giải thích hai thông tin vị trí cần nhập khi báo ca. |
| 31 | [templates/rescue/case_detail.html:66](/home/huy/animal-rescue/templates/rescue/case_detail.html:66) — `Thông tin liên hệ và vị trí` | Chỉ hiện dữ liệu riêng tư cho người đủ quyền. |
| 32 | [templates/rescue/case_detail.html:143](/home/huy/animal-rescue/templates/rescue/case_detail.html:143) — `Khu vực điều phối của quản trị viên` | Đánh dấu khu vực thao tác điều phối và chốt kết quả của quản trị viên. |
| 33 | [templates/rescue/case_messages.html:13](/home/huy/animal-rescue/templates/rescue/case_messages.html:13) — `Khung tin nhắn riêng` | Giải thích phạm vi hiển thị của trang tin nhắn riêng. |

## 2. Các mô tả hàm, lớp và tệp có sẵn

Có **40 chuỗi mô tả sẵn có** đã dịch sang tiếng Việt. Phần nhận nuôi bên dưới là mã cũ đang lưu trữ.

| Vị trí | Hàm/lớp | Ý nghĩa |
| --- | --- | --- |
| [accounts/admin.py:83](/home/huy/animal-rescue/accounts/admin.py:83) | `GroupAdmin` | Chỉ quản trị viên cao nhất được phân quyền sử dụng các chức năng. |
| [accounts/permissions.py:12](/home/huy/animal-rescue/accounts/permissions.py:12) | `is_support_operator` | Kiểm tra tài khoản có quyền làm việc trong khu vực hỗ trợ và cộng tác viên. |
| [accounts/permissions.py:35](/home/huy/animal-rescue/accounts/permissions.py:35) | `support_operator_queryset` | Lấy nhân sự hỗ trợ đang hoạt động, kể cả tài khoản được cấp quyền riêng. |
| [accounts/test_admin_workflow.py:1](/home/huy/animal-rescue/accounts/test_admin_workflow.py:1) | Đầu tệp | Kiểm thử biểu mẫu quản trị tài khoản, nhóm quyền và giới hạn của người được ủy quyền. |
| [adoptions/admin.py:1](/home/huy/animal-rescue/adoptions/admin.py:1) | Đầu tệp | Giữ lại cấu hình quản trị cũ nhưng không đăng ký khi chức năng nhận nuôi đã tắt. |
| [adoptions/middleware.py:14](/home/huy/animal-rescue/adoptions/middleware.py:14) | `AdoptionFollowUpReminderMiddleware` | Định kỳ gửi lời nhắc đến hạn mà không cần tiến trình chạy tác vụ riêng. |
| [adoptions/reminders.py:18](/home/huy/animal-rescue/adoptions/reminders.py:18) | `add_months` | Tính ngày sau số tháng yêu cầu; nếu vượt số ngày trong tháng thì lấy ngày cuối tháng. |
| [adoptions/reminders.py:27](/home/huy/animal-rescue/adoptions/reminders.py:27) | `ensure_follow_up_schedule` | Tạo lịch kiểm tra cố định sau 1, 2 và 3 tháng cho hồ sơ bàn giao nhận nuôi cũ. |
| [adoptions/reminders.py:53](/home/huy/animal-rescue/adoptions/reminders.py:53) | `dispatch_due_follow_up_reminders` | Mỗi lời nhắc đến hạn chỉ được gửi một lần dù bộ lập lịch chạy lặp lại. |
| [config/asgi.py:1](/home/huy/animal-rescue/config/asgi.py:1) | Đầu tệp | Khai báo điểm khởi chạy ASGI của dự án qua biến application. |
| [config/settings.py:1](/home/huy/animal-rescue/config/settings.py:1) | Đầu tệp | Cấu hình Django cho dự án PawRescue. |
| [config/settings.py:9](/home/huy/animal-rescue/config/settings.py:9) | `env_flag` | Đọc biến môi trường dạng đúng/sai theo các giá trị được chấp nhận. |
| [config/settings.py:15](/home/huy/animal-rescue/config/settings.py:15) | `env_list` | Đọc danh sách từ biến môi trường, tách bằng dấu phẩy và bỏ khoảng trắng thừa. |
| [config/test_settings.py:1](/home/huy/animal-rescue/config/test_settings.py:1) | Đầu tệp | Cấu hình kiểm thử tự động với cơ sở dữ liệu và vùng lưu tệp riêng. |
| [config/urls.py:1](/home/huy/animal-rescue/config/urls.py:1) | Đầu tệp | Định tuyến URL chính, chuyển yêu cầu đến các ứng dụng của dự án. |
| [config/wsgi.py:1](/home/huy/animal-rescue/config/wsgi.py:1) | Đầu tệp | Khai báo điểm khởi chạy WSGI của dự án qua biến application. |
| [donations/services.py:16](/home/huy/animal-rescue/donations/services.py:16) | `save_reviewed_donation` | Lưu người duyệt và kết quả duyệt đóng góp nhất quán giữa các giao diện. |
| [donations/storage.py:9](/home/huy/animal-rescue/donations/storage.py:9) | `PrivateDonationStorage` | Kho lưu tệp đóng góp riêng tư, không cung cấp đường dẫn công khai. |
| [donations/uploads.py:14](/home/huy/animal-rescue/donations/uploads.py:14) | `sanitize_receipt_upload` | Kiểm tra nội dung thực của chứng từ thay vì chỉ dựa vào đuôi tệp. |
| [donations/widgets.py:5](/home/huy/animal-rescue/donations/widgets.py:5) | `PrivateAdminFileWidget` | Ô tải tệp lên sử dụng đường dẫn có kiểm tra quyền cho chứng từ riêng tư. |
| [manage.py:2](/home/huy/animal-rescue/manage.py:2) | Đầu tệp | Công cụ dòng lệnh để chạy các tác vụ quản lý Django. |
| [manage.py:8](/home/huy/animal-rescue/manage.py:8) | `main` | Chạy tác vụ quản lý được truyền từ dòng lệnh. |
| [organizations/permissions.py:43](/home/huy/animal-rescue/organizations/permissions.py:43) | `managed_organizations` | Lấy tổ chức đang hoạt động mà người dùng được phép quản lý; dùng chung với mã nhận nuôi cũ. |
| [rescue/admin.py:47](/home/huy/animal-rescue/rescue/admin.py:47) | `ValidatedAdminImageForm` | Hiển thị lỗi tải ảnh ngay trên biểu mẫu trước khi lưu tệp. |
| [rescue/management/__init__.py:1](/home/huy/animal-rescue/rescue/management/__init__.py:1) | Đầu tệp | Các công cụ quản lý dành cho ứng dụng cứu hộ. |
| [rescue/management/commands/__init__.py:1](/home/huy/animal-rescue/rescue/management/commands/__init__.py:1) | Đầu tệp | Các lệnh quản lý riêng của PawRescue. |
| [rescue/notifications.py:56](/home/huy/animal-rescue/rescue/notifications.py:56) | `create_case_notifications` | Tạo một thông báo cho mỗi người nhận, loại trừ người đang thực hiện thao tác. |
| [rescue/storage.py:9](/home/huy/animal-rescue/rescue/storage.py:9) | `PrivateRescueStorage` | Kho ảnh hiện trường chỉ cho tải ảnh sau khi kiểm tra quyền xem ca. |
| [rescue/test_admin_matrix.py:1](/home/huy/animal-rescue/rescue/test_admin_matrix.py:1) | Đầu tệp | Kiểm thử biểu mẫu quản trị bằng hai phiên riêng của quản trị viên và thành viên. |
| [rescue/test_assignment_lifecycle.py:1](/home/huy/animal-rescue/rescue/test_assignment_lifecycle.py:1) | Đầu tệp | Kiểm thử việc thu hồi phân công làm mất quyền xử lý nhưng vẫn giữ lịch sử. |
| [rescue/test_dispatch_workflow.py:1](/home/huy/animal-rescue/rescue/test_dispatch_workflow.py:1) | Đầu tệp | Kiểm thử điều phối cứu hộ và tin nhắn riêng theo ca. |
| [rescue/test_map_coordinates.py:1](/home/huy/animal-rescue/rescue/test_map_coordinates.py:1) | Đầu tệp | Kiểm thử tọa độ trong thuộc tính HTML vẫn được JavaScript đọc đúng khi giao diện dùng tiếng Việt. |
| [rescue/test_simple_case_templates.py:1](/home/huy/animal-rescue/rescue/test_simple_case_templates.py:1) | Đầu tệp | Kiểm tra giao diện cứu hộ gọn vẫn giữ thao tác thật và giới hạn theo vai trò. |
| [rescue/test_two_account_journey.py:19](/home/huy/animal-rescue/rescue/test_two_account_journey.py:19) | `AdminAndGuestJourneyTests` | Kiểm thử hành trình báo tin, tiếp nhận, phân công và đánh giá kết quả cuối cùng. |
| [rescue/uploads.py:175](/home/huy/animal-rescue/rescue/uploads.py:175) | `sanitize_image_upload` | Kiểm tra nội dung ảnh và loại bỏ thông tin phụ EXIF hoặc văn bản được nhúng trong ảnh. |
| [rescue/uploads.py:208](/home/huy/animal-rescue/rescue/uploads.py:208) | `sanitize_model_image` | Chuẩn hóa ảnh mới được gắn vào đối tượng trước khi ghi tệp vào kho lưu trữ. |
| [scripts/qa_finance_postgres.py:1](/home/huy/animal-rescue/scripts/qa_finance_postgres.py:1) | Đầu tệp | Kiểm thử luồng tài chính và quản trị trên cơ sở dữ liệu đang cấu hình. |
| [scripts/run_postgres_audit.py:1](/home/huy/animal-rescue/scripts/run_postgres_audit.py:1) | Đầu tệp | Chạy kiểm thử Django trong vùng dữ liệu PostgreSQL tạm, không tạo cơ sở dữ liệu mới. |
| [support/test_admin_workflow.py:1](/home/huy/animal-rescue/support/test_admin_workflow.py:1) | Đầu tệp | Kiểm thử quản trị hỗ trợ và quyền riêng tư của hội thoại. |
| [support/views.py:117](/home/huy/animal-rescue/support/views.py:117) | `_lock_operator_conversation` | Khóa bản ghi hội thoại gốc rồi kiểm tra lại quyền của người phụ trách. |

Hai mô tả đầu tệp của công cụ kiểm thử PostgreSQL cũng được dùng cho phần hướng dẫn `--help`.

Xem [thứ tự trình bày và demo](HUONG_DAN_DOC_CODE.md) để theo dõi luồng website hiện tại.
