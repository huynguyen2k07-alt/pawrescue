# Phân quyền và bảo vệ dữ liệu PawRescue

Tài liệu giải thích thông tin nào được xem theo từng vai trò. Quyền được kiểm tra ở máy chủ khi xem hồ sơ, đọc chat, tải ảnh và nhận thông báo; ẩn nút trên giao diện không thay thế kiểm tra quyền.

## 1. Các vai trò

| Vai trò | Công việc chính | Phạm vi |
| --- | --- | --- |
| Khách/người dùng không liên quan | Xem thông tin cứu hộ công khai | Bản xem chung, không có hồ sơ gốc của người khác |
| Người báo tin | Gửi và theo dõi tin của mình | Nội dung đã gửi, ảnh ban đầu, liên hệ của chính mình và trạng thái xử lý |
| Cộng tác viên cứu hộ | Đại diện trung tâm hoặc người hỗ trợ ngoài hiện trường | Chỉ các ca đang được admin giao; xác minh và báo kết quả |
| Admin chính | Điều phối, giao việc và duyệt kết quả cuối | Hồ sơ và các thao tác quản lý theo quyền admin |
| Nhân viên hỗ trợ nội bộ | Trả lời các cuộc trò chuyện được giao | Chỉ hộp thư được admin phân công; không tự đọc hàng đợi chưa được giao |

Trong mã hiện tại, `moderator` là **cộng tác viên cứu hộ**. `collaborator` là vai trò cũ dành cho **nhân viên hỗ trợ nội bộ**. Hai vai trò này không được tự động đổi cho nhau vì quyền đọc hộp thư khác nhau. Nhân sự cứu hộ không có quyền quản trị Django hoặc tự cấp quyền admin.

## 2. Ai được xem thông tin gì?

Trong bảng dưới, “CTV được giao” là người có phân công **đang hoạt động** trên đúng ca đó.

| Thông tin/thao tác | Khách hoặc người dùng khác | Người báo tin của ca | CTV được giao | Admin chính |
| --- | --- | --- | --- | --- |
| Tin mới chưa xác minh | Không | Có | Có | Có |
| Trạng thái và thời gian của hồ sơ đã công khai | Có | Có | Có | Có |
| Tiêu đề/nội dung/đặc điểm gốc do người báo nhập | Không; chỉ thấy bản tóm tắt chung | Có | Có | Có |
| Họ tên, email, số điện thoại người báo | Không | Của mình | Có trên ca được giao | Có |
| Địa chỉ cụ thể và tọa độ chính xác | Không | Của mình | Có trên ca được giao | Có |
| Ảnh hiện trường ban đầu | Không | Của mình | Có trên ca được giao | Có |
| Ghi chú xác minh, đánh giá và nhật ký nội bộ | Không | Không | Có trên ca được giao | Có |
| Ảnh cập nhật do đội cứu hộ gửi | Không | Không | Có trên ca được giao | Có |
| Chỉ dẫn và chat riêng admin ↔ CTV | Không | Không | Chỉ tin mình gửi/nhận | Chỉ tin mình gửi/nhận |
| Giao/thu hồi người xử lý, chuyển đơn vị | Không | Không | Không | Có |
| Xác minh hoặc báo hoàn thành | Không | Không | Có trên ca được giao | Có |
| Duyệt cứu hộ thành công và công khai kết quả | Không | Không | Không | Có |
| Tạo tài khoản/cấp quyền admin | Không | Không | Không | Có |

CTV bị thu hồi phân công mất quyền xem hồ sơ gốc và trao đổi nội bộ của ca. Hoàn thành ca không biến số điện thoại và địa chỉ của người báo thành dữ liệu công khai.

## 3. Trang công khai và bản đồ

- Chỉ các ca đã được admin chính duyệt **cứu hộ thành công** xuất hiện trên bản đồ thành công.
- Khách và người dùng khác nhìn thấy vị trí **gần đúng**, không nhận tọa độ hiện trường chính xác trong HTML hoặc dữ liệu bản đồ.
- Quy tắc này áp dụng cả hồ sơ cũ có `is_location_private=False`.
- Thẻ ca/trang chi tiết công khai dùng tiêu đề chung theo loại động vật và mã ca. Không đưa nguyên văn nội dung người báo vào trang công khai vì nội dung đó có thể chứa số điện thoại, email hoặc địa chỉ.
- Tìm kiếm công khai chỉ dựa vào dữ liệu được phép công khai. Tìm thử một địa chỉ riêng không được làm lộ việc địa chỉ ấy có trong hồ sơ.
- Ảnh hiện trường có thể chứa mặt người, biển số hoặc số nhà. Hiện chưa có bước duyệt ảnh công khai riêng, nên ảnh gốc chỉ được cấp cho người có quyền; bản xem công khai dùng hình thay thế.

## 4. Chat và thông báo

- Khung chat được dùng chung trên giao diện, nhưng **chat hỗ trợ client** và **chat điều phối theo ca** là hai luồng dữ liệu riêng.
- Người báo không đọc được chỉ dẫn hay tin nhắn admin ↔ CTV. Một CTV không đọc được tin admin gửi riêng cho CTV khác.
- Tài khoản chỉ được mở hội thoại hoặc tải tệp của hội thoại có quyền truy cập. Đổi mã ca, mã ảnh hay mã hội thoại trong URL không cấp thêm quyền.
- Hội thoại client chưa giao chỉ hiện với admin chính và chỉ thông báo cho admin chính. Nhân viên hỗ trợ chỉ nhận nội dung của hội thoại được giao đúng tài khoản.
- Thông báo gửi người báo chỉ báo sự kiện/trạng thái, không trích ghi chú đánh giá hoặc nhật ký hiện trường nội bộ. Thông báo cũ đã lưu ghi chú riêng cũng được dựng lại tiêu đề/nội dung an toàn khi hiển thị hoặc trả notice tự cập nhật; không sửa mất dữ liệu lịch sử.
- Khi thu hồi/chuyển phân công, các thông báo cũ liên quan dữ liệu riêng cũng phải được kiểm tra lại theo quyền hiện tại.
- Các trang có dữ liệu riêng và tệp chat dùng `no-store`; trang phụ thuộc tài khoản có `Vary: Cookie` để hạn chế dùng lại nội dung qua bộ nhớ đệm.

## 5. Các phần khác

- Góp ý: nội dung và email người gửi dành cho admin; không phải danh sách góp ý công khai.
- Đóng góp: thông tin chuyển khoản nhận ủng hộ được công khai có chủ đích. Email người đóng góp, mã giao dịch và ảnh xác nhận không phải dữ liệu công khai. Tên/lời nhắn/số tiền chỉ xuất hiện theo chính sách đóng góp đã xác nhận và lựa chọn ẩn danh.
- Biên lai chi phí: chỉ công khai khi người quản lý chủ động bật công khai; phải kiểm tra và che dữ liệu cá nhân trên biên lai trước khi bật.
- Kiến thức/đội ngũ: chỉ đăng nội dung giới thiệu được phép công khai; không chép số điện thoại cá nhân hoặc dữ liệu hồ sơ cứu hộ vào nội dung giới thiệu.
- Tệp cấu hình `.env`, cơ sở dữ liệu, tệp chat và báo cáo kiểm thử cục bộ không đưa lên GitHub.

## 6. Tự kiểm tra khi trình bày đồ án

1. Mở ba phiên đăng nhập riêng: người báo, CTV được giao và admin chính; thêm một phiên khách hoặc client khác.
2. Gửi một ca thử có số điện thoại và địa chỉ giả dễ nhận biết. Ghi lại mã ca.
3. Giao cho CTV, gửi chỉ dẫn riêng, trao đổi trong khung chat và thử báo hoàn thành.
4. Trước admin duyệt: ca chưa được đưa lên bản đồ thành công. Sau admin duyệt: khách chỉ thấy thông tin chung và vị trí gần đúng.
5. Dùng client khác/khách mở cùng URL, mã ảnh, chat và thông báo: không nhận dữ liệu riêng.
6. Thu hồi CTV rồi thử mở lại hồ sơ/chat/tệp/thông báo cũ: dữ liệu nội bộ không còn được cấp.
7. Gửi một tin chat client chưa giao: chỉ admin nhận; sau admin giao hộp thư, chỉ đúng nhân viên hỗ trợ nhận được.

Các kiểm thử tự động liên quan:

```bash
.venv/bin/python manage.py test rescue.test_public_privacy_review support.test_privacy_assignment --settings=config.test_settings
```

Kiểm thử này dùng dữ liệu giả và CSDL kiểm thử riêng. Không dùng thao tác xóa hay dữ liệu riêng của người thật để minh họa đồ án.

## 7. Phạm vi và giới hạn

Đây là chính sách phân quyền ứng dụng và các biện pháp đã kiểm tra trong mã; không phải cam kết hệ thống an toàn tuyệt đối. Người đã có quyền xem vẫn có thể chụp màn hình hoặc chép thông tin, nên tài khoản và thiết bị của đội cứu hộ phải được quản lý phù hợp.

Bản chạy ở máy cá nhân có thể bật `DJANGO_DEBUG=true` phục vụ phát triển. Khi triển khai công khai cần cấu hình môi trường sản xuất: tắt debug, dùng HTTPS, khóa bí mật riêng, giới hạn host/origin, bảo vệ tài khoản admin, sao lưu CSDL và không phục vụ `private_media` trực tiếp qua web server. Thư mục dữ liệu và quyền truy cập hệ điều hành/CSDL là lớp bảo vệ riêng, ngoài việc ẩn thông tin trên giao diện.


## 8. Tài liệu tham khảo

- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): giới hạn quyền theo nhu cầu, kiểm tra quyền trên từng yêu cầu và từng đối tượng.
- [Django 5.2 — Security](https://docs.djangoproject.com/en/5.2/topics/security/): các lớp bảo vệ của Django và yêu cầu cấu hình khi triển khai.
