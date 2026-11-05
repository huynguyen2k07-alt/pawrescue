# Tìm địa chỉ bằng Geoapify và tùy chọn Google Maps

Cập nhật 02/11/2026. Website hiện tìm địa chỉ bằng **Geoapify**, dùng Leaflet/OpenStreetMap để hiển thị và chỉnh ghim. Google Maps Platform là lựa chọn tích hợp khác trong tương lai; source hiện tại chưa gọi dịch vụ này. Liên kết mở Google Maps trong hồ sơ chỉ mở tọa độ được phép xem, không dùng API key và không đăng địa điểm lên Google.

## Cấu hình Geoapify đang dùng

1. Tạo khóa cho dự án trong [Geoapify MyProjects](https://myprojects.geoapify.com/).
2. Lưu khóa trong `.env` ở thư mục dự án bằng biến `GEOAPIFY_API_KEY`. Không dán khóa vào mã nguồn, JavaScript, chat hoặc GitHub. Ví dụ này chỉ là chỗ giữ, không phải khóa thật:

   ```dotenv
   GEOAPIFY_API_KEY=dan_key_cua_ban_vao_day
   ```

3. Khởi động lại server nếu cấu hình mới chưa có hiệu lực. Thiếu khóa thì nút tìm địa chỉ được ẩn; các cách đặt ghim khác vẫn dùng được.
4. Đăng nhập, mở form báo ca, nhập địa chỉ/mốc tại Đà Nẵng, bấm **Tìm địa chỉ trên bản đồ** rồi tự chọn gợi ý. Kiểm tra/kéo ghim, tự tick xác nhận địa chỉ đúng hiện trường rồi mới gửi báo cáo.

Trình duyệt chỉ gọi **POST `/locations/search/`** của website với phiên đăng nhập và CSRF; máy chủ mới gọi Geoapify bằng khóa. Không đưa khóa hay URL có khóa xuống HTML/JavaScript. Không tự gọi khi đang gõ; chọn gợi ý không thay địa chỉ/mốc đã nhập và không tự tick xác nhận. Kết quả tối đa năm gợi ý được giới hạn trong vùng tiếp nhận Đà Nẵng: vĩ độ `15.85–16.25`, kinh độ `107.75–108.35`. Địa chỉ tìm kiếm được gửi tới Geoapify; form có liên kết ghi nguồn dịch vụ.

Gói Free tại thời điểm tra cứu **02/11/2026** có **3.000 credits/ngày**, yêu cầu giữ liên kết ghi nguồn (attribution) và có quota. Xem [bảng giá Geoapify](https://www.geoapify.com/pricing/) để kiểm tra điều kiện hiện hành. Cache một giờ và giới hạn lượt gọi trong ứng dụng giúp giảm tiêu hao; khi dịch vụ lỗi hoặc hết quota, người báo vẫn đặt ghim/nhập tọa độ và xác nhận để gửi. Thử chức năng với dữ liệu giả trên môi trường QA; tìm kiếm chỉ gợi ý, không tự tạo hồ sơ cứu hộ.

## Google Cloud — chỉ dùng khi quyết định tích hợp thêm

Các bước dưới đây là hướng dẫn chuẩn bị tùy chọn. Chúng chưa bật tính năng Google Maps trong source hiện tại và không cần thực hiện để dùng Geoapify.

1. Mở [Google Cloud Console](https://console.cloud.google.com/), đăng nhập và tạo project `animal-rescue`.
2. Vào **Billing**, liên kết tài khoản thanh toán cho project. Bản tích hợp dùng thực tế có thể phát sinh phí theo lượng sử dụng. [Hướng dẫn thiết lập của Google](https://developers.google.com/maps/documentation/javascript/get-api-key).
3. Vào **APIs & Services → Library**, bật **Maps JavaScript API** và **Places API (New)**. Maps hiển thị bản đồ; Places hỗ trợ tìm/chọn địa chỉ. [Điều kiện của Place Autocomplete](https://developers.google.com/maps/documentation/javascript/place-autocomplete-new).
4. Vào **APIs & Services → Credentials → Create credentials → API key**.
5. Mở phần chỉnh key, chọn **Application restrictions → Websites**, thêm:

   ```text
   http://localhost:8000/*
   http://127.0.0.1:8000/*
   ```

   Khi triển khai, thêm đúng tên miền HTTPS của website. Ở **API restrictions**, chọn **Restrict key** và chỉ cho phép hai API vừa bật. Lưu thay đổi. [Hướng dẫn giới hạn key](https://developers.google.com/maps/api-security-best-practices).
6. Lưu key trong file `.env` tại thư mục dự án, không dán vào chat hoặc đưa lên GitHub:

   ```dotenv
   GOOGLE_MAPS_API_KEY=dan_key_cua_ban_vao_day
   ```

   `.env` hiện đã được dự án bỏ qua trong Git. Đây là tên biến dự kiến cho tùy chọn Google; source hiện tại chưa đọc biến này. Tạo key Google không thay cho cấu hình `GEOAPIFY_API_KEY` đang dùng.

Nên đặt cảnh báo ngân sách và quota phù hợp. Cảnh báo ngân sách không tự động là mức trần chặn mọi chi phí. Không cần bật API khác nếu chức năng chưa dùng tới.

## Độ chính xác

[Ví dụ định vị trên web của Google](https://developers.google.com/maps/documentation/javascript/geolocation) vẫn dùng Geolocation của trình duyệt. Chuyển nền bản đồ hoặc dùng Geoapify không tự làm kết quả laptop sai số 1.226 m thành chính xác vài mét. Geoapify và Places giúp tìm địa chỉ/số nhà; người báo vẫn cần kiểm tra ghim đúng hiện trường và tự xác nhận trước khi gửi. Admin/người được phân công nhận tọa độ được lưu trong hồ sơ theo quyền; không có cam kết sai số GPS bằng không.
