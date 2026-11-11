# Mục lục chú thích tiếng Việt — PawRescue

**Bắt đầu từ bảng 1.** Bấm vào vị trí để mở đúng dòng code. Trong trình soạn thảo, tìm `CHỨC NĂNG CHÍNH` để nhảy giữa các khối nổi bật.

Các chú thích tập trung vào chức năng chính và những bước kiểm tra quyền quan trọng. Một khối tiêu đề + một câu giải thích được tính là một ghi chú, không phải chú thích từng dòng.

## Bổ sung ngày 10/11: chat và quyền riêng tư

| Phần quan trọng | Mở chú thích | Công dụng |
| --- | --- | --- |
| Bảo vệ hồ sơ công khai | [rescue/privacy.py:40](/home/huy/animal-rescue/rescue/privacy.py:40) | `present_case` chỉ trả bản xem chung cho khách/client khác; giữ số điện thoại, địa chỉ, nội dung gốc và ảnh cho đúng người có quyền. |
| Chat admin ↔ cộng tác viên | [static/js/support-chat.js:386](/home/huy/animal-rescue/static/js/support-chat.js:386) | Dùng khung chat góc dưới, mỗi ca có luồng riêng và kiểm tra người nhận ở máy chủ. |
| Thông báo cũ chứa ghi chú riêng | [rescue/notifications.py:11](/home/huy/animal-rescue/rescue/notifications.py:11) | Dựng nội dung an toàn theo quyền hiện tại trước khi hiển thị HTML hoặc notice tự cập nhật. |

Đọc [bảng phân quyền và bảo mật](/home/huy/animal-rescue/docs/PHAN_QUYEN_VA_BAO_MAT.md) để biết từng vai trò được xem gì.

## 1. CHỨC NĂNG CHÍNH — MỞ NHANH

| STT | Chức năng nổi bật | Vị trí và hàm | Tác dụng |
| --- | --- | --- | --- |
| 1 | **ĐĂNG KÝ TÀI KHOẢN** | [accounts/views.py:18](/home/huy/animal-rescue/accounts/views.py:18) — `register` | Form kiểm tra dữ liệu và chỉ tạo người dùng thường, sau đó đăng nhập bằng phiên Django. |
| 2 | **PHÂN QUYỀN ĐIỀU PHỐI CỨU HỘ** | [rescue/permissions.py:11](/home/huy/animal-rescue/rescue/permissions.py:11) — `is_rescue_admin` | Quyền điều hành cứu hộ chỉ dành cho tài khoản quản trị cao nhất đang hoạt động. |
| 3 | **KIỂM TRA VỊ TRÍ BÁO TIN** | [rescue/forms.py:127](/home/huy/animal-rescue/rescue/forms.py:127) — `RescueCaseForm.clean` | Tin báo phải có đủ tọa độ trong phạm vi Đà Nẵng để xác định đúng hiện trường. |
| 4 | **GỬI YÊU CẦU CỨU HỘ** | [rescue/views.py:657](/home/huy/animal-rescue/rescue/views.py:657) — `case_create` | Lưu tin báo cùng ảnh trong một giao dịch rồi thông báo cho quản trị viên tiếp nhận. |
| 5 | **CHỌN VỊ TRÍ TRÊN BẢN ĐỒ** | [static/js/maps.js:500](/home/huy/animal-rescue/static/js/maps.js:500) — `setLocation` | Giữ ghim và ô tọa độ đồng bộ khi bấm bản đồ, kéo ghim hoặc lấy vị trí thiết bị. |
| 6 | **BẢN ĐỒ CA CỨU HỘ THÀNH CÔNG** | [rescue/views.py:583](/home/huy/animal-rescue/rescue/views.py:583) — `case_map` | Chỉ đưa ca đã chốt cứu thành công vào cả danh sách và dữ liệu bản đồ công khai. |
| 7 | **XEM HỒ SƠ CỨU HỘ** | [rescue/views.py:424](/home/huy/animal-rescue/rescue/views.py:424) — `case_detail` | Hiển thị liên hệ, vị trí chính xác và thao tác xử lý theo quyền của người xem. |
| 8 | **GIAO CA VÀ NHẮN CỘNG TÁC VIÊN** | [rescue/views.py:1067](/home/huy/animal-rescue/rescue/views.py:1067) — `case_notify_admins` | Admin chính tạo hoặc kích hoạt phân công và gửi tin riêng cho các cộng tác viên cứu hộ đang hoạt động; không tự xác minh hoặc công khai tin báo. |
| 9 | **TIẾP NHẬN YÊU CẦU** | [rescue/views.py:848](/home/huy/animal-rescue/rescue/views.py:848) — `case_claim` | Quản trị viên tiếp nhận tin báo và thông báo cho người gửi sau khi xác minh. |
| 10 | **NGƯỜI DÙNG GỬI TIN NHẮN HỖ TRỢ** | [support/views.py:286](/home/huy/animal-rescue/support/views.py:286) — `chat_send` | Khóa tài khoản trước khi tìm hoặc tạo hội thoại để tránh mở trùng khi gửi đồng thời. |
| 11 | **QUẢN TRỊ VIÊN PHẢN HỒI NGƯỜI DÙNG** | [support/views.py:500](/home/huy/animal-rescue/support/views.py:500) — `admin_reply` | Kiểm tra người được xử lý hội thoại, lưu câu trả lời và giữ liên kết về đúng ca cứu hộ. |
| 12 | **BÀN GIAO ĐƠN VỊ CỨU HỘ** | [rescue/views.py:907](/home/huy/animal-rescue/rescue/views.py:907) — `case_handoff` | Bàn giao cho đơn vị bên ngoài nhưng giữ lịch sử và quyền chốt kết quả ở quản trị viên. |
| 13 | **PHÂN CÔNG NGƯỜI PHỤ TRÁCH** | [rescue/views.py:1187](/home/huy/animal-rescue/rescue/views.py:1187) — `case_assign` | Admin chính giao ca cho người đủ điều kiện; giao cộng tác viên cứu hộ không tự xác minh tin reported. |
| 14 | **NHẮN TIN ĐIỀU PHỐI** | [rescue/views.py:1294](/home/huy/animal-rescue/rescue/views.py:1294) — `case_messages` | Admin chính trao đổi với người đang được giao ca; mỗi người chỉ đọc tin mình gửi hoặc nhận. |
| 15 | **CẬP NHẬT NHẬT KÝ CỨU HỘ** | [rescue/views.py:801](/home/huy/animal-rescue/rescue/views.py:801) — `case_add_update` | Quản trị viên hoặc người còn được phân công mới được ghi nhật ký cho ca chưa chốt. |
| 16 | **ĐÁNH GIÁ VÀ CHỐT CA** | [rescue/views.py:992](/home/huy/animal-rescue/rescue/views.py:992) — `case_update_status` | Cộng tác viên được giao xác minh và báo pending_review; chỉ admin chính duyệt rescued để công khai vị trí. |
| 17 | **TỪ CHỐI HỒ SƠ CỨU HỘ** | [rescue/views.py:1142](/home/huy/animal-rescue/rescue/views.py:1142) — `case_reject` | Admin chính hoặc cộng tác viên được giao mở xác nhận rồi xóa tin không hợp lệ khi có lý do; thông báo cho admin chính và người báo tin vẫn tồn tại sau xóa. |
| 18 | **THU HỒI PHÂN CÔNG** | [rescue/views.py:1368](/home/huy/animal-rescue/rescue/views.py:1368) — `case_unassign` | Thu hồi quyền xử lý bằng cách kết thúc phân công, giữ nguyên lịch sử và trao đổi cũ. |
| 19 | **LƯU TRẠNG THÁI VÀ LỊCH SỬ CỨU HỘ** | [rescue/models.py:106](/home/huy/animal-rescue/rescue/models.py:106) — `RescueCase.change_status` | Lưu trạng thái, thời điểm chốt và lịch sử cùng nhau để hồ sơ cứu hộ luôn nhất quán. |
| 20 | **TIẾP NHẬN GÓP Ý** | [rescue/views.py:219](/home/huy/animal-rescue/rescue/views.py:219) — `case_list` | Lưu góp ý và thông báo riêng cho quản trị viên để theo dõi xử lý. |
| 21 | **HIỂN THỊ THÔNG TIN ỦNG HỘ** | [donations/context_processors.py:5](/home/huy/animal-rescue/donations/context_processors.py:5) — `donation_footer` | Chỉ công khai tài khoản ngân hàng đầy đủ của quỹ đang hoạt động thuộc tổ chức đã xác minh. |
| 22 | **DUYỆT KHOẢN ĐÓNG GÓP** | [donations/services.py:17](/home/huy/animal-rescue/donations/services.py:17) — `save_reviewed_donation` | Mọi giao diện dùng chung giao dịch duyệt để nhất quán người duyệt, tổng quỹ và thông báo. |
| 23 | **LẤY SỐ LIỆU CỨU HỘ CÔNG KHAI** | [rescue/statistics.py:100](/home/huy/animal-rescue/rescue/statistics.py:100) — `_public_case_counts` | Chỉ đếm trạng thái và ngày nhận request trong một truy vấn; không đọc nội dung hay thông tin riêng của hồ sơ. |
| 24 | **CHUẨN HÓA SỐ LIỆU THEO NGÀY** | [rescue/statistics.py:122](/home/huy/animal-rescue/rescue/statistics.py:122) — `_daily_series` | Pandas điền số 0 cho ngày trống, nhờ đó biểu đồ luôn đủ bảy ngày liên tiếp. |
| 25 | **VẼ VÀ LƯU ĐỆM BIỂU ĐỒ** | [rescue/statistics.py:133](/home/huy/animal-rescue/rescue/statistics.py:133) — `get_public_rescue_statistics` | Gộp thành ba nhóm; chỉ vẽ lại khi số liệu hoặc ngày đổi, các lần khác dùng lại ảnh. |
| 26 | **ĐỒNG BỘ BIỂU ĐỒ VỚI TRÌNH DUYỆT** | [rescue/statistics.py:186](/home/huy/animal-rescue/rescue/statistics.py:186) — `public_statistics_state` | Mã phiên bản không đổi thì chỉ báo 304, tránh gửi lại hai ảnh sau mỗi năm giây. |
| 27 | **TỰ CẬP NHẬT BIỂU ĐỒ** | [static/js/public-statistics.js:52](/home/huy/animal-rescue/static/js/public-statistics.js:52) — `schedule` | Chỉ kiểm tra định kỳ khi trang đang mở và có mạng; mỗi lần chỉ chạy một yêu cầu. |
| 28 | **KIỂM TRA DỮ LIỆU BIỂU ĐỒ** | [static/js/public-statistics.js:109](/home/huy/animal-rescue/static/js/public-statistics.js:109) — `validPayload` | Kiểm tra đủ ảnh PNG, số đếm và bảy ngày liên tiếp trước khi thay số liệu đang hiển thị. |
| 29 | **HIỂN THỊ SỐ LIỆU MỚI** | [static/js/public-statistics.js:141](/home/huy/animal-rescue/static/js/public-statistics.js:141) — `render` | Chỉ cập nhật số liệu; giữ nguyên phần đang mở, vị trí đọc và liên kết trên trang. |
| 30 | **ĐỐI CHIẾU PHIÊN BẢN DỮ LIỆU** | [static/js/public-statistics.js:174](/home/huy/animal-rescue/static/js/public-statistics.js:174) — `refresh` | Mã 304 nghĩa là dữ liệu chưa đổi: chỉ cập nhật giờ kiểm tra, giữ nguyên biểu đồ và bảng. |
| 31 | **LẤY VỊ TRÍ THIẾT BỊ VÀ CÓ THỂ HỦY** | [static/js/maps.js:149](/home/huy/animal-rescue/static/js/maps.js:149) — `bindLocationButton` | Yêu cầu vị trí mới, chính xác cao ngay từ đầu; giữ kết quả có sai số nhỏ nhất trong thời gian chờ, không tự sửa tọa độ hay giảm sai số. Sai số lớn chỉ hiện xem trước; hủy/chỉnh ghim sẽ bỏ qua kết quả muộn. |
| 32 | **ĐÁNH DẤU THÔNG BÁO NGAY TẠI DANH SÁCH** | [rescue/views.py:762](/home/huy/animal-rescue/rescue/views.py:762) — `_notification_read_response` | Trả số đếm mới cho JavaScript; không chuyển trang khi đánh dấu. Khi tắt JavaScript, giữ bộ lọc và trang đang đọc. |
| 33 | **CẬP NHẬT THÔNG BÁO TRÊN MỌI TRANG** | [rescue/notification_live.py:88](/home/huy/animal-rescue/rescue/notification_live.py:88) — `notification_state` | Chỉ trả số đếm và tiêu đề theo quyền hiện tại; có ETag để không gửi lại dữ liệu khi chưa đổi. |
| 34 | **KIỂM TRA THÔNG BÁO RIÊNG TRƯỚC KHI HIỂN THỊ** | [static/js/notifications-live.js:88](/home/huy/animal-rescue/static/js/notifications-live.js:88) — `validateState` | Kiểm tra tài khoản, số đếm, dữ liệu và liên kết trước khi thay đổi giao diện. |
| 35 | **TỰ CẬP NHẬT THÔNG BÁO Ở MỌI TRANG** | [static/js/notifications-live.js:296](/home/huy/animal-rescue/static/js/notifications-live.js:296) — `refresh` | Kiểm tra khoảng hai giây, hiện notice và đổi bộ đếm; không tải lại trang, không gửi yêu cầu chồng nhau. |
| 36 | **TÌM ĐỊA CHỈ QUA MÁY CHỦ** | [rescue/geocoding.py:182](/home/huy/animal-rescue/rescue/geocoding.py:182) — `address_search` | Kiểm tra đăng nhập/CSRF, giới hạn lượt tìm và lưu đệm gợi ý Đà Nẵng; giữ API key phía server, không tạo tin báo. |
| 37 | **TÌM ĐỊA CHỈ VÀ CHỌN GHIM** | [static/js/address-search.js:1](/home/huy/animal-rescue/static/js/address-search.js:1) | Chỉ tìm khi bấm nút; chọn gợi ý đặt ghim, giữ địa chỉ/mốc và chờ người báo tự kiểm tra/xác nhận. Hủy phản hồi cũ khi đổi cách chọn vị trí. |

## 2. Ghi chú bảo vệ dữ liệu và hỗ trợ

| STT | Vị trí và hàm/khu vực | Tác dụng |
| --- | --- | --- |
| 1 | [accounts/admin.py:63](/home/huy/animal-rescue/accounts/admin.py:63) — `UserAdmin.get_readonly_fields` | Chỉ admin chính cấp vai trò/quyền quản trị; người được ủy quyền không tự nâng quyền. |
| 2 | [accounts/views.py:52](/home/huy/animal-rescue/accounts/views.py:52) — `collaborator_dashboard` | Quản trị viên cứu hộ chỉ xem ca đang được giao trong khu vực làm việc; quyền hộp thư hỗ trợ được kiểm tra riêng. |
| 3 | [config/admin_site.py:25](/home/huy/animal-rescue/config/admin_site.py:25) — `RescueAdminSite.get_app_list` | Thu gọn menu về chức năng chính và giữ việc kiểm tra quyền của từng chức năng. |
| 4 | [rescue/forms.py:172](/home/huy/animal-rescue/rescue/forms.py:172) — `CaseStatusUpdateForm.clean` | Báo hoàn thành hoặc chốt thành công cần đánh giá và vị trí hợp lệ; admin chính duyệt thì ca mới lên bản đồ. |
| 5 | [rescue/permissions.py:36](/home/huy/animal-rescue/rescue/permissions.py:36) — `visible_cases_for` | Giữ riêng tin báo chưa được tiếp nhận cho những người liên quan. |
| 6 | [rescue/permissions.py:49](/home/huy/animal-rescue/rescue/permissions.py:49) — `eligible_assignees` | Lọc quản trị viên cứu hộ, nhân sự hỗ trợ và người quản lý tổ chức đủ điều kiện nhận ca. |
| 7 | [rescue/storage.py:29](/home/huy/animal-rescue/rescue/storage.py:29) — `PrivateRescueStorage.url` | Bắt buộc kiểm tra quyền khi tải ảnh hiện trường. |
| 8 | [rescue/uploads.py:176](/home/huy/animal-rescue/rescue/uploads.py:176) — `sanitize_image_upload` | Kiểm tra tệp tải lên và hạn chế lộ thông tin được nhúng trong ảnh. |
| 9 | [rescue/views.py:146](/home/huy/animal-rescue/rescue/views.py:146) — `_display_coordinates` | Bảo vệ vị trí nhạy cảm khi hiển thị bản đồ. |
| 10 | [rescue/views.py:188](/home/huy/animal-rescue/rescue/views.py:188) — `case_image` | Ngăn tải ảnh của ca bằng đường dẫn khi không có quyền xem ca. |
| 11 | [static/admin/js/support-inbox.js:142](/home/huy/animal-rescue/static/admin/js/support-inbox.js:142) — `refreshInbox` | Cập nhật quyền truy cập và nút thao tác khi hội thoại thay đổi. |
| 12 | [static/js/maps.js:15](/home/huy/animal-rescue/static/js/maps.js:15) — `isWithinDaNang` | Giới hạn vị trí người dùng chọn theo khu vực tiếp nhận. |
| 13 | [static/js/maps.js:41](/home/huy/animal-rescue/static/js/maps.js:41) — `getTileProviders` | Ưu tiên lớp bản đồ mặc định không phụ thuộc khóa dịch vụ. |
| 14 | [static/js/maps.js:618](/home/huy/animal-rescue/static/js/maps.js:618) — `initDetailMap` | Hiển thị đúng vị trí gần đúng do máy chủ cung cấp. |
| 15 | [static/js/maps.js:651](/home/huy/animal-rescue/static/js/maps.js:651) — `buildPopup` | Mở ảnh, địa chỉ theo quyền, đơn vị và thời điểm duyệt trên ghim; chèn bằng văn bản để không thực thi nội dung nhập. |
| 16 | [static/js/support-chat.js:105](/home/huy/animal-rescue/static/js/support-chat.js:105) — `renderMessages` | Cập nhật khung hỗ trợ khi một tin cũ được sửa hoặc thay đổi tệp. |
| 17 | [support/views.py:35](/home/huy/animal-rescue/support/views.py:35) — `_operator_ids` | Giữ riêng thông báo của hội thoại đã được phân công. |
| 18 | [support/views.py:110](/home/huy/animal-rescue/support/views.py:110) — `_case_for_conversation` | Chỉ ghép ca của đúng người báo tin và chỉ cho người có quyền xem ca đó. |
| 19 | [support/views.py:127](/home/huy/animal-rescue/support/views.py:127) — `_lock_operator_conversation` | Ngăn xử lý nhầm khi nhiều người cùng thao tác hoặc đổi phân công. |
| 20 | [templates/rescue/case_detail.html:66](/home/huy/animal-rescue/templates/rescue/case_detail.html:66) — `Thông tin liên hệ và vị trí` | Chỉ hiện dữ liệu riêng tư cho người đủ quyền. |
| 21 | [templates/rescue/case_detail.html:145](/home/huy/animal-rescue/templates/rescue/case_detail.html:145) — `Khu vực duyệt kết quả của admin chính` | Admin chính đọc báo cáo và duyệt kết quả trước khi công khai ca thành công. |
| 22 | [templates/rescue/case_detail.html:233](/home/huy/animal-rescue/templates/rescue/case_detail.html:233) — `Khu vực xử lý ca của quản trị viên` | Quản trị viên xác minh, báo hoàn thành hoặc từ chối ca được giao; không tự duyệt thành công. |
| 23 | [templates/rescue/case_form.html:18](/home/huy/animal-rescue/templates/rescue/case_form.html:18) — `Biểu mẫu báo ca` | Giải thích hai thông tin vị trí cần nhập khi báo ca. |
| 24 | [templates/rescue/case_messages.html:13](/home/huy/animal-rescue/templates/rescue/case_messages.html:13) — `Khung tin nhắn riêng` | Giải thích phạm vi hiển thị của trang tin nhắn riêng. |
| 25 | [static/js/notifications-live.js:352](/home/huy/animal-rescue/static/js/notifications-live.js:352) — `Xử lý submit đánh dấu đọc` | Gửi POST có CSRF, cập nhật ngay tại danh sách, hủy phản hồi kiểm tra cũ và cho thử lại khi lỗi. |
| 26 | [static/js/maps.js:451](/home/huy/animal-rescue/static/js/maps.js:451) — `showApproximateLocation` | Hiện dấu hỏi màu xám/vùng sai số lớn để chỉnh, phân biệt với ghim đã chọn; chưa ghi tọa độ gửi admin, không ghi đè điểm đã chọn. |
| 27 | [rescue/forms.py:67](/home/huy/animal-rescue/rescue/forms.py:67) — `RescueCaseForm.__init__` | Bắt buộc người báo kiểm tra ghim/địa chỉ khi gửi ca mới; GPS gần đúng chưa đủ để điều phối. |
| 28 | [rescue/geocoding.py:84](/home/huy/animal-rescue/rescue/geocoding.py:84) — `_read_body` | Giới hạn dung lượng và thời gian đọc để nguồn tìm địa chỉ lỗi không giữ kết nối quá lâu. |
| 29 | [rescue/geocoding.py:199](/home/huy/animal-rescue/rescue/geocoding.py:199) — `address_search` | Hạn chế lượt gọi Geoapify trong từng giây bằng cache; khi chạy nhiều worker cần cache dùng chung. |

## 3. Mô tả hàm, lớp và tệp

Có **56 chuỗi mô tả** bằng tiếng Việt. Phần nhận nuôi là mã cũ đang lưu trữ, không phải chức năng đang bật.

| Vị trí | Hàm/lớp | Ý nghĩa |
| --- | --- | --- |
| [accounts/admin.py:84](/home/huy/animal-rescue/accounts/admin.py:84) | `GroupAdmin` | Chỉ quản trị viên cao nhất được phân quyền sử dụng các chức năng. |
| [accounts/permissions.py:12](/home/huy/animal-rescue/accounts/permissions.py:12) | `is_support_operator` | Kiểm tra tài khoản có quyền làm việc trong khu vực hỗ trợ và cộng tác viên. |
| [accounts/permissions.py:37](/home/huy/animal-rescue/accounts/permissions.py:37) | `support_operator_queryset` | Lấy nhân sự hỗ trợ đang hoạt động, kể cả tài khoản được cấp quyền riêng. |
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
| [donations/test_moderator_access.py:1](/home/huy/animal-rescue/donations/test_moderator_access.py:1) | Đầu tệp | Quản trị viên cứu hộ không được mở chứng từ riêng hoặc nhận điều phối quỹ. |
| [donations/uploads.py:14](/home/huy/animal-rescue/donations/uploads.py:14) | `sanitize_receipt_upload` | Kiểm tra nội dung thực của chứng từ thay vì chỉ dựa vào đuôi tệp. |
| [donations/widgets.py:5](/home/huy/animal-rescue/donations/widgets.py:5) | `PrivateAdminFileWidget` | Ô tải tệp lên sử dụng đường dẫn có kiểm tra quyền cho chứng từ riêng tư. |
| [manage.py:2](/home/huy/animal-rescue/manage.py:2) | Đầu tệp | Công cụ dòng lệnh để chạy các tác vụ quản lý Django. |
| [manage.py:8](/home/huy/animal-rescue/manage.py:8) | `main` | Chạy tác vụ quản lý được truyền từ dòng lệnh. |
| [organizations/permissions.py:47](/home/huy/animal-rescue/organizations/permissions.py:47) | `managed_organizations` | Lấy tổ chức đang hoạt động mà người dùng được phép quản lý; dùng chung với mã nhận nuôi cũ. |
| [rescue/admin.py:47](/home/huy/animal-rescue/rescue/admin.py:47) | `ValidatedAdminImageForm` | Hiển thị lỗi tải ảnh ngay trên biểu mẫu trước khi lưu tệp. |
| [rescue/management/__init__.py:1](/home/huy/animal-rescue/rescue/management/__init__.py:1) | Đầu tệp | Các công cụ quản lý dành cho ứng dụng cứu hộ. |
| [rescue/management/commands/__init__.py:1](/home/huy/animal-rescue/rescue/management/commands/__init__.py:1) | Đầu tệp | Các lệnh quản lý riêng của PawRescue. |
| [rescue/notifications.py:56](/home/huy/animal-rescue/rescue/notifications.py:56) | `create_case_notifications` | Tạo một thông báo cho mỗi người nhận, loại trừ người đang thực hiện thao tác. |
| [rescue/statistics.py:1](/home/huy/animal-rescue/rescue/statistics.py:1) | Đầu tệp | Tổng hợp số liệu cứu hộ công khai và dựng biểu đồ cho trang chủ. |
| [rescue/storage.py:9](/home/huy/animal-rescue/rescue/storage.py:9) | `PrivateRescueStorage` | Kho ảnh hiện trường chỉ cho tải ảnh sau khi kiểm tra quyền xem ca. |
| [rescue/test_admin_handoff_completion.py:1](/home/huy/animal-rescue/rescue/test_admin_handoff_completion.py:1) | Đầu tệp | Kiểm thử gửi ca cho quản trị viên được phân công và chốt thành công lên bản đồ. |
| [rescue/test_admin_matrix.py:1](/home/huy/animal-rescue/rescue/test_admin_matrix.py:1) | Đầu tệp | Kiểm thử biểu mẫu quản trị bằng hai phiên riêng của quản trị viên và thành viên. |
| [rescue/test_assignment_lifecycle.py:1](/home/huy/animal-rescue/rescue/test_assignment_lifecycle.py:1) | Đầu tệp | Kiểm thử việc thu hồi phân công làm mất quyền xử lý nhưng vẫn giữ lịch sử. |
| [rescue/test_dispatch_workflow.py:1](/home/huy/animal-rescue/rescue/test_dispatch_workflow.py:1) | Đầu tệp | Kiểm thử điều phối cứu hộ và tin nhắn riêng theo ca. |
| [rescue/test_map_coordinates.py:1](/home/huy/animal-rescue/rescue/test_map_coordinates.py:1) | Đầu tệp | Kiểm thử tọa độ trong thuộc tính HTML vẫn được JavaScript đọc đúng khi giao diện dùng tiếng Việt. |
| [rescue/test_moderator_workflow.py:1](/home/huy/animal-rescue/rescue/test_moderator_workflow.py:1) | Đầu tệp | Kiểm tra quản trị viên xử lý ca được giao, còn admin chính duyệt kết quả. |
| [rescue/test_public_statistics.py:1](/home/huy/animal-rescue/rescue/test_public_statistics.py:1) | Đầu tệp | Kiểm tra số liệu công khai, mốc ngày và bộ nhớ đệm của biểu đồ cứu hộ. |
| [rescue/test_public_status_groups.py:1](/home/huy/animal-rescue/rescue/test_public_status_groups.py:1) | Đầu tệp | Kiểm tra các mục tin báo không trùng nhau và biểu đồ chỉ có ba nhóm số liệu. |
| [rescue/test_simple_case_templates.py:1](/home/huy/animal-rescue/rescue/test_simple_case_templates.py:1) | Đầu tệp | Kiểm tra giao diện cứu hộ gọn vẫn giữ thao tác thật và giới hạn theo vai trò. |
| [rescue/test_successful_map.py:1](/home/huy/animal-rescue/rescue/test_successful_map.py:1) | Đầu tệp | Kiểm tra bản đồ tổng chỉ chứa ca cứu thành công và vẫn bảo vệ vị trí riêng tư. |
| [rescue/test_two_account_journey.py:19](/home/huy/animal-rescue/rescue/test_two_account_journey.py:19) | `AdminAndGuestJourneyTests` | Kiểm thử hành trình báo tin, tiếp nhận, phân công và đánh giá kết quả cuối cùng. |
| [rescue/uploads.py:175](/home/huy/animal-rescue/rescue/uploads.py:175) | `sanitize_image_upload` | Kiểm tra nội dung ảnh và loại bỏ thông tin phụ EXIF hoặc văn bản được nhúng trong ảnh. |
| [rescue/uploads.py:208](/home/huy/animal-rescue/rescue/uploads.py:208) | `sanitize_model_image` | Chuẩn hóa ảnh mới được gắn vào đối tượng trước khi ghi tệp vào kho lưu trữ. |
| [scripts/qa_finance_postgres.py:1](/home/huy/animal-rescue/scripts/qa_finance_postgres.py:1) | Đầu tệp | Kiểm thử luồng tài chính và quản trị trên cơ sở dữ liệu đang cấu hình. |
| [scripts/run_postgres_audit.py:1](/home/huy/animal-rescue/scripts/run_postgres_audit.py:1) | Đầu tệp | Chạy kiểm thử Django trong vùng dữ liệu PostgreSQL tạm, không tạo cơ sở dữ liệu mới. |
| [support/test_admin_workflow.py:1](/home/huy/animal-rescue/support/test_admin_workflow.py:1) | Đầu tệp | Kiểm thử quản trị hỗ trợ và quyền riêng tư của hội thoại. |
| [support/views.py:121](/home/huy/animal-rescue/support/views.py:121) | `_lock_operator_conversation` | Khóa bản ghi hội thoại gốc rồi kiểm tra lại quyền của người phụ trách. |
| [rescue/notification_live.py:1](/home/huy/animal-rescue/rescue/notification_live.py:1) | Đầu tệp | Cung cấp thông báo mới cho chuông chung của website và trang quản trị. |
| [rescue/notification_live.py:21](/home/huy/animal-rescue/rescue/notification_live.py:21) | `notification_destination` | Trả liên kết nội bộ an toàn cho thông báo ở cả HTML và dữ liệu cập nhật. |
| [rescue/test_notification_live.py:1](/home/huy/animal-rescue/rescue/test_notification_live.py:1) | Đầu tệp | Kiểm tra đồng bộ thông báo không tải lại trang và không lộ thông tin riêng. |
| [rescue/test_notification_live_templates.py:1](/home/huy/animal-rescue/rescue/test_notification_live_templates.py:1) | Đầu tệp | Kiểm tra thông báo tự cập nhật có mặt trên mọi khu vực và giữ đúng quyền xem. |
| [rescue/test_location_confirmation.py:1](/home/huy/animal-rescue/rescue/test_location_confirmation.py:1) | Đầu tệp | Tin báo chỉ được gửi sau khi người báo kiểm tra ghim và địa chỉ hiện trường. |

| [rescue/geocoding.py:1](/home/huy/animal-rescue/rescue/geocoding.py:1) | Đầu tệp | Tìm địa chỉ Đà Nẵng qua Geoapify mà không đưa khóa dịch vụ ra trình duyệt. |
| [rescue/test_geocoding.py:1](/home/huy/animal-rescue/rescue/test_geocoding.py:1) | Đầu tệp | Kiểm thử đăng nhập, giới hạn tìm, lỗi dịch vụ và bảo vệ khóa bằng dữ liệu giả; không gọi dịch vụ thật. |
| [rescue/test_guest_location_journey.py:1](/home/huy/animal-rescue/rescue/test_guest_location_journey.py:1) | Đầu tệp | Đăng ký và đăng nhập người dùng thường, tìm/chọn vị trí rồi kiểm tra admin/người được giao ca nhận đúng địa chỉ và tọa độ đã lưu; không đo GPS thật. |
| [rescue/test_request_delivery.py:1](/home/huy/animal-rescue/rescue/test_request_delivery.py:1) | Đầu tệp | Kiểm tra báo lỗi khi gửi chưa hợp lệ, mã hồ sơ và luồng client → admin → quản trị viên qua các phiên/hostname riêng, không thao tác trình duyệt thật. |

Xem [lộ trình học và trình bày đồ án](HUONG_DAN_DOC_CODE.md) để đọc theo luồng xử lý của website.
