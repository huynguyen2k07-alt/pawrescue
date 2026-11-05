# HỌC CODE VÀ TRÌNH BÀY ĐỒ ÁN PAWRESCUE

**Luồng cần nhớ:** Người dùng báo tin → admin chính giao ca → quản trị viên xác minh hoặc từ chối → cứu hộ và báo hoàn thành → admin chính duyệt kết quả → ca thành công lên bản đồ.

**Phân biệt vai trò:** admin chính giữ quyền điều phối, duyệt và quản trị toàn hệ thống. Quản trị viên cứu hộ có vai trò `moderator`, xem ca được giao, xác minh tin báo, báo kết quả hoặc từ chối tin không hợp lệ; tài khoản này không dùng quyền `is_staff`/`is_superuser` và không có hộp thư hỗ trợ chung. Cộng tác viên hỗ trợ là vai trò khác, không tự có quyền xác minh hoặc duyệt ca.

## 1. TÌM NOTE NỔI BẬT

Tìm cụm `CHỨC NĂNG CHÍNH` trong code. Mỗi phần quan trọng có tiêu đề lớn và một câu giải thích tiếng Việt, ví dụ:

```python
# ===== CHỨC NĂNG CHÍNH: GỬI YÊU CẦU CỨU HỘ =====
# Lưu tin báo cùng ảnh trong một giao dịch rồi thông báo cho quản trị viên tiếp nhận.
```

Mở [mục lục chú thích](DANH_SACH_CHU_THICH.md) để bấm đến đúng dòng. Bảng đầu tập hợp các phần chính; các ghi chú kiểm tra quyền/tệp riêng và mô tả mã cũ nằm phía sau.

## 2. ĐỌC CODE THEO ĐƯỜNG ĐI CỦA MỘT YÊU CẦU

1. **URL** chọn hàm xử lý: đọc `config/urls.py`, rồi `rescue/urls.py`.
2. **Form** kiểm tra dữ liệu người nhập: đọc `RescueCaseForm` trong `rescue/forms.py`.
3. **View** xử lý nghiệp vụ: đọc `case_create` trong `rescue/views.py`.
4. **Model** lưu dữ liệu: đọc `RescueCase` và `RescueCaseImage` trong `rescue/models.py`.
5. **Template** dựng giao diện: đọc `templates/rescue/case_form.html`, `case_detail.html` và `templates/base.html`.
6. **JavaScript** cập nhật ngay trên trình duyệt: bản đồ ở `static/js/maps.js`, tìm địa chỉ ở `static/js/address-search.js`, biểu đồ ở `static/js/public-statistics.js`. Riêng tìm địa chỉ đi qua `rescue/geocoding.py` trước khi gọi Geoapify.

Bắt đầu bằng việc gửi một ca QA rồi lần theo sáu bước trên. Hiểu một luồng trọn vẹn trước khi đọc quỹ hoặc các trang quản trị phụ.

## 3. CHỨC NĂNG CHÍNH — BẤM ĐỂ MỞ CODE

| Phần cần học | Mở note trong code | Điều cần giải thích |
| --- | --- | --- |
| **ĐĂNG KÝ** | [accounts/views.py → register](/home/huy/animal-rescue/accounts/views.py:18) | Kiểm tra form, tạo người dùng thường và đăng nhập bằng phiên Django. |
| **KIỂM TRA BÁO TIN** | [rescue/forms.py → RescueCaseForm.clean](/home/huy/animal-rescue/rescue/forms.py:127) | Bắt buộc địa chỉ và ghim hợp lệ; chặn tọa độ ngoài khu vực tiếp nhận. |
| **GỬI YÊU CẦU** | [rescue/views.py → case_create](/home/huy/animal-rescue/rescue/views.py:652) | Gắn người báo từ tài khoản đang đăng nhập, lưu ca/ảnh rồi báo admin. |
| **CHỌN VỊ TRÍ BÁO TIN** | [static/js/maps.js → setLocation](/home/huy/animal-rescue/static/js/maps.js:500) | Bấm hoặc kéo ghim sẽ đồng bộ với hai ô tọa độ của tin báo. |
| **LẤY VỊ TRÍ THIẾT BỊ** | [static/js/maps.js → bindLocationButton](/home/huy/animal-rescue/static/js/maps.js:149) | Lấy nhanh và theo dõi chính xác trong một lần bấm; hiện sai số, chỉ cải thiện ghim và dừng khi chọn thủ công. |
| **TÌM ĐỊA CHỈ PHÍA MÁY CHỦ** | [rescue/geocoding.py → address_search](/home/huy/animal-rescue/rescue/geocoding.py:181) | POST cần đăng nhập/CSRF; giữ Geoapify key ở server, kiểm tra địa chỉ và chỉ trả tối đa năm gợi ý trong vùng Đà Nẵng. |
| **CHỌN GỢI Ý ĐỊA CHỈ** | [static/js/address-search.js → search](/home/huy/animal-rescue/static/js/address-search.js:110) | Chỉ tìm khi bấm nút; chọn gợi ý đặt ghim qua `maps.js`, giữ nguyên địa chỉ/mốc và yêu cầu người báo tự kiểm tra, xác nhận. |
| **ĐÁNH DẤU ĐỌC TẠI CHỖ** | [rescue/views.py → _notification_read_response](/home/huy/animal-rescue/rescue/views.py:753) | POST trả số đếm mới để giữ nguyên danh sách; không chuyển sang nội dung khi đánh dấu. |
| **API THÔNG BÁO CHUNG** | [rescue/notification_live.py → notification_state](/home/huy/animal-rescue/rescue/notification_live.py:88) | Lấy dữ liệu riêng đúng tài khoản, giữ việc đánh dấu đọc ở POST; 304 khi chưa đổi. |
| **NOTICE KHÔNG CẦN TẢI LẠI** | [static/js/notifications-live.js → refresh](/home/huy/animal-rescue/static/js/notifications-live.js:296) | Đổi chuông, hiện notice mới trên web/admin; dừng khi ẩn tab, mất mạng hoặc hết phiên. |
| **BẢN ĐỒ CÔNG KHAI** | [rescue/views.py → case_map](/home/huy/animal-rescue/rescue/views.py:581) | `/map/` chỉ lấy ca được admin chốt cứu thành công (`rescued`), kể cả khi admin xem. Vị trí ca đang điều phối được xem trong hồ sơ riêng theo quyền. |
| **PHÂN QUYỀN** | [rescue/permissions.py → is_rescue_admin](/home/huy/animal-rescue/rescue/permissions.py:11) | `is_rescue_admin` kiểm tra admin chính; `is_rescue_moderator` và `can_review_case` giới hạn quản trị viên vào ca đang được giao. |
| **KHU VỰC CA ĐƯỢC GIAO** | [accounts/views.py → collaborator_dashboard](/home/huy/animal-rescue/accounts/views.py:51) | Quản trị viên chỉ thấy ca đang được giao trong khu vực làm việc; quyền hộp thư hỗ trợ được kiểm tra riêng. |
| **HỒ SƠ CA** | [rescue/views.py → case_detail](/home/huy/animal-rescue/rescue/views.py:429) | Quyết định ai được thấy liên hệ, vị trí, phân công và các nút xử lý. |
| **TIẾP NHẬN** | [rescue/views.py → case_claim](/home/huy/animal-rescue/rescue/views.py:841) | Admin xác minh và tiếp nhận; không nhân thông báo khi thao tác lặp. |
| **GỬI CA CHO QUẢN TRỊ VIÊN** | [rescue/views.py → case_notify_admins](/home/huy/animal-rescue/rescue/views.py:1064) | Admin chính tạo/kích hoạt phân công và gửi tin riêng cho các `moderator` đang hoạt động; tin `reported` chưa được coi là xác minh. Bấm lặp không nhân tin khi nội dung và phân công còn nguyên. |
| **CHAT HỖ TRỢ** | [support/views.py → chat_send](/home/huy/animal-rescue/support/views.py:274) | Người báo gửi tin và tệp, có kiểm tra quyền và chống tạo trùng hội thoại. |
| **PHẢN HỒI** | [support/views.py → admin_reply](/home/huy/animal-rescue/support/views.py:500) | Người hỗ trợ được phép trả lời và giữ liên kết về đúng ca. |
| **BÀN GIAO** | [rescue/views.py → case_handoff](/home/huy/animal-rescue/rescue/views.py:900) | Chọn đơn vị hợp lệ, kết thúc phân công cũ và ghi lịch sử. |
| **PHÂN CÔNG** | [rescue/views.py → case_assign](/home/huy/animal-rescue/rescue/views.py:1184) | Chọn đúng nhân sự đủ điều kiện, gửi chỉ dẫn riêng. |
| **TIN ĐIỀU PHỐI** | [rescue/views.py → case_messages](/home/huy/animal-rescue/rescue/views.py:1254) | Admin chính trao đổi riêng với người đang được giao ca; mỗi người chỉ đọc tin mình gửi/nhận, khác hộp thư hỗ trợ người báo. |
| **NHẬT KÝ** | [rescue/views.py → case_add_update](/home/huy/animal-rescue/rescue/views.py:794) | Người được giao hoặc admin cập nhật hiện trường khi ca chưa chốt. |
| **XÁC MINH / BÁO KẾT QUẢ / DUYỆT** | [rescue/views.py → case_update_status](/home/huy/animal-rescue/rescue/views.py:986) | Quản trị viên được giao chuyển tin sang `verified` rồi báo `pending_review` kèm đánh giá; chỉ admin chính duyệt `rescued` để công khai vị trí. |
| **TỪ CHỐI VÀ XÓA TIN BÁO** | [rescue/views.py → case_reject](/home/huy/animal-rescue/rescue/views.py:1139) | Trang GET chỉ hỏi xác nhận; POST cần lý do và xác nhận xóa. Quản trị viên chỉ từ chối ca được giao, chưa chốt/chưa chờ duyệt; thông báo lý do tồn tại sau khi xóa ca. |
| **THU HỒI** | [rescue/views.py → case_unassign](/home/huy/animal-rescue/rescue/views.py:1317) | Mất quyền xử lý hiện tại nhưng giữ lịch sử để đối chiếu. |
| **LƯU LỊCH SỬ** | [rescue/models.py → RescueCase.change_status](/home/huy/animal-rescue/rescue/models.py:106) | Đồng bộ trạng thái, thời điểm chốt và lịch sử trong cùng giao dịch. |
| **GÓP Ý** | [rescue/views.py → case_list](/home/huy/animal-rescue/rescue/views.py:303) | Form góp ý trên trang chủ lưu vào CSDL và thông báo cho admin. |
| **DONATE CUỐI TRANG** | [donations/context_processors.py → donation_footer](/home/huy/animal-rescue/donations/context_processors.py:5) | Chỉ hiện ngân hàng đầy đủ của chiến dịch đang hoạt động, tổ chức đã xác minh. |
| **DUYỆT ĐÓNG GÓP** | [donations/services.py → save_reviewed_donation](/home/huy/animal-rescue/donations/services.py:17) | Dùng chung quy tắc người duyệt, tổng tiền và thông báo cho web/admin. |

Bản đồ tổng hợp lưu lại các điểm cứu hộ thành công. Tin mới báo, đã xác nhận, đã phân công, đang cứu hộ hoặc **đang chờ duyệt kết quả** chưa xuất hiện trên `/map/`; ca hủy hoặc chỉ đóng hồ sơ cũng không xuất hiện. Bản đồ nhỏ trong hồ sơ và liên kết Google Maps vẫn hỗ trợ xem vị trí theo quyền. Liên kết Google Maps được tạo từ tọa độ đã qua bước làm gần đúng, không lấy tọa độ riêng tư để gửi cho người ngoài và không tự đăng địa điểm lên dịch vụ bên ngoài.

**Nút Dùng vị trí hiện tại:** chỉ bắt đầu khi người dùng bấm, không theo dõi lúc mở trang. Lấy nhanh với vị trí còn mới tối đa 10 giây; đồng thời dùng `watchPosition` chính xác cao nếu đã có quyền. Khi quyền đang chờ, chỉ yêu cầu nhanh mở hộp thoại; sau khi được cấp quyền mới bắt đầu theo dõi chính xác. Dành tối đa 30 giây chờ cấp quyền/phản hồi đầu, rồi tối đa 15 giây lấy và cải thiện vị trí. Kết quả trong vùng hợp lệ, có sai số tối đa 1.000 m, được đặt ghim ngay và luôn ghi sai số ước tính. Chỉ thay ghim khi sai số giảm; đạt sai số tối đa 50 m thì dừng, còn vị trí gần đúng sau khi hết chờ phải kiểm tra ghim. Với sai số trên 1.000 m, `showApproximateLocation` hiện dấu hỏi màu xám ghi rõ chưa chọn hiện trường và vòng sai số, chưa ghi hai ô tọa độ; người dùng kéo ghim/bấm bản đồ/nhập tọa độ thì mới xác nhận và dừng GPS. Không ghi đè ghim đã chọn bằng vị trí sai số lớn. Thiếu độ chính xác hợp lệ không tự điền. Khi hai lượt lấy vị trí đều báo lỗi, dừng chờ và báo đúng loại lỗi; không đưa nguyên thông báo kỹ thuật của nhà cung cấp ra giao diện. Lỗi khởi tạo nền/ghim bản đồ được bắt riêng để nút GPS và nhập tọa độ tiếp tục dùng được. Nếu không có API theo dõi, dùng một lần lấy chính xác cao thay thế. Hủy, chỉnh ghim, sửa tọa độ, ẩn tab hoặc rời trang sẽ dừng theo dõi và bỏ qua kết quả muộn. Quyền vị trí còn phụ thuộc trình duyệt, HTTPS/localhost và hệ điều hành; laptop không bảo đảm có vị trí chính xác tức thì. Không dùng DNS/IP hoặc ghim mặc định để giả kết quả. Nút tìm gần tôi dùng chung cơ chế này nhưng không giới hạn vị trí người xem trong vùng báo tin.

**Chọn vị trí ngay trong website:** nhập địa chỉ cụ thể/mốc nhận biết, bấm **Tìm địa chỉ trên bản đồ**, chọn gợi ý rồi kiểm tra/kéo ghim. Chọn gợi ý giữ nguyên chữ đã nhập, không tự thay địa chỉ bằng nhãn nhà cung cấp và không tự tick `location_confirmed`. Có thể dùng **Dùng vị trí hiện tại** hoặc bấm vào bản đồ để đặt ghim. Hai ô tọa độ thủ công nằm trong phần thu gọn để dùng khi bản đồ không tải được hoặc trình duyệt tắt JavaScript; form Django vẫn kiểm tra tọa độ khi gửi. Leaflet 1.9.4 cùng giấy phép gốc lưu tại `static/vendor/leaflet/`; ảnh nền cần mạng. Giao diện không yêu cầu chọn nhà cung cấp nền. Ghim thành công dùng `buildPopup` hiển thị ảnh, địa chỉ theo quyền, đơn vị và thời điểm duyệt, rồi dẫn đến hồ sơ bằng liên kết bình thường.

**Đường đi tìm địa chỉ Geoapify:** `config/settings.py` đọc `GEOAPIFY_API_KEY` từ `.env`; có thể phải khởi động lại server khi đổi biến. `case_create` chỉ truyền cờ bật/tắt để template hiện nút, không truyền khóa. Bấm nút mới khiến `address-search.js` gửi địa chỉ bằng POST cùng CSRF đến `/locations/search/`; gõ chữ không gọi dịch vụ. `address_search` yêu cầu đăng nhập, nhận địa chỉ 5–300 ký tự sau chuẩn hóa, gọi URL Geoapify cố định và chỉ trả nhãn cùng tọa độ. Phạm vi được lọc và kiểm tra lại ở server là vĩ độ `15.85–16.25`, kinh độ `107.75–108.35`; đây là vùng tiếp nhận của dự án. Khóa, URL chứa khóa và lỗi kỹ thuật không được trả ra giao diện. Form ghi rõ địa chỉ tìm kiếm được gửi tới Geoapify và có liên kết ghi nguồn.

Kết quả tối đa năm gợi ý được cache một giờ; mỗi người có khoảng chờ hai giây khi truy vấn chưa có cache, tổng lượt gọi được giới hạn bằng năm slot trong một giây. Cache mặc định có phạm vi từng process; khi triển khai nhiều worker cần cache dùng chung. Nhà cung cấp có quota riêng; lỗi mạng, quá thời gian, thiếu khóa hoặc hết quota chỉ báo lỗi tìm kiếm để người dùng vẫn chọn ghim/nhập tọa độ. Máy chủ đặt timeout kết nối/đọc sáu giây; DNS của hệ điều hành có thể chậm hơn, nên không bảo đảm tổng thời gian chờ tuyệt đối. Trình duyệt hủy tìm sau bảy giây. Tìm kiếm không tạo ca/ảnh/thông báo. Geoapify đổi địa chỉ thành vị trí gợi ý, không cải thiện phép đo GPS của laptop và không bảo đảm đúng hiện trường.

**Tránh kết quả cũ ghi đè ghim mới:** bắt đầu tìm địa chỉ sẽ dừng GPS đang chờ. Bấm GPS, chọn/kéo ghim hoặc sửa tọa độ sẽ hủy tìm địa chỉ; sửa địa chỉ xóa gợi ý cũ. Hai script bỏ qua callback thuộc lượt đã hủy; ẩn tab hoặc rời trang cũng hủy. Đổi vị trí/địa chỉ, bắt đầu tìm hoặc lấy GPS lại sẽ bỏ dấu xác nhận cũ. Sau cùng người báo tự kiểm tra, tick xác nhận và gửi; admin/người được giao ca nhận địa chỉ cùng tọa độ đã lưu theo quyền.

**Thông báo tự cập nhật trên mọi trang:** các chức năng đang tạo `Notification` dùng chung chuông và notice mới. API [rescue/notification_live.py → notification_state](/home/huy/animal-rescue/rescue/notification_live.py:88) chỉ lấy dữ liệu từ `available_notifications` theo tài khoản và quyền hiện tại, không gửi nội dung trao đổi, địa chỉ hoặc liên hệ. Trình duyệt kiểm tra khoảng 2 giây khi trang đang mở; dữ liệu không đổi trả 304. Khi có tin mới, đổi bộ đếm và hiện notice bằng văn bản; không tải lại trang hay xóa form đang nhập. Hết phiên hoặc đổi tài khoản thì dừng và xóa dữ liệu riêng đang hiển thị. Danh sách trang đầu cập nhật theo bộ lọc; trang cũ giữ nội dung để người dùng đọc tiếp. Liên kết xem hỗ trợ chuột giữa. Nút **Đánh dấu đã đọc** hoặc **Đánh dấu tất cả đã đọc** gửi POST có CSRF và dùng chung `notification_snapshot` để đổi số đếm ngay, giữ nguyên trang/vị trí đọc; lỗi mạng thì giữ nút cho phép thử lại. Tắt JavaScript vẫn quay về bộ lọc và trang danh sách đang đọc. Bộ đếm tin nhắn hỗ trợ được giữ riêng vì trạng thái đọc khác thông báo.

Nút **Gửi ca cho các quản trị viên** tạo hoặc kích hoạt lại phân công để người nhận mở được tin mới chưa xác minh. Nếu phân công còn hiệu lực và cùng nội dung đã gửi thì không tạo tin trùng; khi giao lại cho người đã bị thu hồi, người đó được nhận thông báo lại. Quản trị viên dùng **Xác nhận thông tin** để xác minh, rồi **Báo đã hoàn thành** sau khi cứu hộ. Báo cáo `pending_review` giữ người báo kết quả, thời điểm và ghi chú; ở bước này quản trị viên chờ admin chính duyệt, chưa công khai điểm trên bản đồ.

`CaseStatusUpdateForm.clean` kiểm tra đánh giá và vị trí hợp lệ khi báo hoàn thành hoặc chốt thành công. Các kiểm tra này chạy phía máy chủ, kể cả POST trực tiếp hoặc endpoint quản trị cũ. Admin chính đọc báo cáo, ghi đánh giá duyệt rồi bấm **Duyệt thành công và công khai**. Nếu từ chối tin không hợp lệ bằng **Từ chối và xóa tin báo**, GET chưa xóa; POST cần xác nhận cùng lý do và để lại thông báo cho admin chính/người báo tin.

**Phân biệt bấm gửi và gửi thành công:** `case_create` chỉ lưu ca/ảnh và tạo thông báo sau khi `form.is_valid()` đạt. Form sai hiện bảng lỗi đầu trang và autofocus mục đầu tiên cần sửa, giữ dữ liệu đã nhập. Thành công chuyển tới hồ sơ và báo mã ca; chưa có mã ca, vẫn ở form thì cần sửa lỗi trước khi admin nhận được tin.

## 4. RIÊNG PHẦN BIỂU ĐỒ PYTHON

1. **Lấy số liệu:** [rescue/statistics.py → _public_case_counts](/home/huy/animal-rescue/rescue/statistics.py:100) đếm trạng thái/ngày nhận request trong một truy vấn, kể cả request chưa duyệt; không đọc nội dung, liên hệ hoặc địa chỉ.
2. **Chuẩn hóa ngày:** [rescue/statistics.py → _daily_series](/home/huy/animal-rescue/rescue/statistics.py:122) dùng Pandas điền số 0 cho ngày trống, giữ đủ 7 ngày.
3. **Tính và vẽ:** [rescue/statistics.py → get_public_rescue_statistics](/home/huy/animal-rescue/rescue/statistics.py:133) dùng NumPy tính tổng/trung bình, gọi Matplotlib vẽ hai ảnh và dùng lại ảnh khi dữ liệu không đổi.
4. **Trả dữ liệu cho web:** [rescue/statistics.py → public_statistics_state](/home/huy/animal-rescue/rescue/statistics.py:186) trả JSON; nếu mã phiên bản không đổi thì trả 304 để không gửi lại ảnh.
5. **Tự cập nhật:** [static/js/public-statistics.js → schedule](/home/huy/animal-rescue/static/js/public-statistics.js:52) kiểm tra mỗi 5 giây; [static/js/public-statistics.js → render](/home/huy/animal-rescue/static/js/public-statistics.js:141) chỉ đổi số liệu/ảnh, giữ nguyên phần người dùng đang mở.

Qua 0 giờ theo múi giờ website, khung 7 ngày tự thêm ngày mới và bỏ ngày cũ nhất. Khi mất mạng hoặc ẩn tab, cập nhật tạm dừng rồi tự tiếp tục. GUI của dự án là giao diện web HTML/CSS; biểu đồ được Python tạo ra và đưa vào GUI đó.

Biểu đồ và bảng trạng thái chỉ hiện ba nhóm: **Đã xác nhận** là request đã nhận nhưng chưa chốt (gồm `reported`, `verified`, `assigned`, `in_progress`, `pending_review`); **Đã cứu thành công** là `rescued`; **Đã hủy** gồm `cancelled` và `closed`. Một ca chỉ nằm trong một nhóm. Chuyển giữa các bước đang xử lý không đổi ba nhóm nên dùng lại biểu đồ; nhận request mới, chốt kết quả, xóa hồ sơ hoặc đổi ngày sẽ cập nhật số liệu khi có thay đổi.

Trong danh sách tin báo, **Chờ xác nhận** chỉ chứa `reported`; **Đã phê duyệt** chứa các bước đang xử lý còn lại. Hai tab này không trùng ca. Quyền xem tin chưa duyệt không đổi: chỉ người báo, admin chính và người còn được giao ca thấy nội dung. Quy tắc bản đồ `/map/` vẫn chỉ lấy `rescued`, sau khi admin chính duyệt thành công.

## 5. TỪ KHÓA ĐỂ ĐỌC CODE

| Từ khóa | Hiểu ngắn gọn |
| --- | --- |
| `GET` / `POST` | GET thường mở trang/lấy số liệu; POST gửi yêu cầu tạo hoặc sửa dữ liệu. |
| `form.is_valid()` | Chạy kiểm tra dữ liệu trước khi lưu. |
| `form.cleaned_data` | Dữ liệu sau khi được form kiểm tra. |
| `form.save(commit=False)` | Tạo đối tượng trong bộ nhớ để gắn thêm người báo tin trước khi lưu CSDL. |
| `Model.objects` | Truy vấn bảng dữ liệu tương ứng. |
| `transaction.atomic()` | Lưu các phần liên quan cùng nhau; lỗi thì hoàn tác giao dịch. |
| `select_for_update()` | Khóa bản ghi trong giao dịch để hai thao tác đồng thời không xử lý chồng. |
| `render()` / `redirect()` | Trả giao diện / chuyển sang URL khác sau khi xử lý. |
| Hàm bắt đầu bằng `_` | Hàm hỗ trợ trong module; đọc khi muốn hiểu chi tiết một bước. |

## 6. TRÌNH TỰ DEMO

1. Trên dữ liệu QA, người dùng nhập địa chỉ/mốc → bấm **Tìm địa chỉ trên bản đồ** → chọn gợi ý → kiểm tra/kéo ghim → tự tick xác nhận → gửi tin; ca ở trạng thái `reported`. Địa chỉ/mốc vẫn giữ nguyên sau khi chọn gợi ý. Nếu dịch vụ tìm lỗi, dùng GPS, bấm ghim hoặc nhập tọa độ rồi kiểm tra trước khi gửi.
2. Admin chính bấm **Gửi ca cho các quản trị viên**. Mở tài khoản `moderator` tại `/collaborators/`, kiểm tra ca vừa được giao và tin nhắn riêng; việc giao ca chưa xác minh hoặc công khai tin.
3. Quản trị viên bấm **Xác nhận thông tin**, trao đổi với admin chính và cập nhật hiện trường. Dùng một ca QA khác để thử **Từ chối và xóa tin báo**: mở xác nhận, hủy, rồi xác nhận kèm lý do; kiểm tra thông báo vẫn còn sau khi xóa.
4. Sau cứu hộ, quản trị viên ghi đánh giá và **Báo đã hoàn thành**. Xem lịch sử ghi tác giả/thời điểm; ca chuyển `pending_review`, khóa thao tác sửa của quản trị viên và chưa xuất hiện trên bản đồ.
5. Admin chính xem báo cáo, ghi đánh giá rồi **Duyệt thành công và công khai**. Mở `/map/` để thấy ca `rescued`, bấm ghim để xem ảnh, địa chỉ, đơn vị và thời điểm duyệt; thử liên kết Google Maps trong hồ sơ bằng người ngoài và người có quyền để đối chiếu vị trí gần đúng/chính xác.
6. Mở lịch sử và để trang chủ tự cập nhật biểu đồ sau thay đổi. Ca hủy, chỉ đóng hoặc còn chờ duyệt không xuất hiện trên bản đồ thành công.

**Cần nhớ khi giải thích quyền:** admin chính đang hoạt động có `is_superuser`, giữ việc điều phối, duyệt kết quả và quản trị tài khoản/quỹ/tổ chức. Quản trị viên cứu hộ dùng `role="moderator"`, không có `is_staff`/`is_superuser` hoặc quyền hỗ trợ chung; chỉ xử lý ca đang được giao. Việc giao ca và việc xác minh là hai bước riêng. Đơn vị bên ngoài không cần tài khoản để được ghi nhận bàn giao. Email bàn giao chỉ mở bản nháp để admin chính xem và tự gửi.

Các biểu mẫu hiện tại giữ một nút lưu; liên kết hỗ trợ mở tab mới. Xóa bài có trang xác nhận. Không sửa `.venv/`, dữ liệu `media/`, `private_media/` hoặc migration cũ để học chức năng web.

**Quyền tạo tài khoản quản trị:** đăng ký công khai chỉ có email, họ tên, điện thoại và mật khẩu; mọi trường tự chèn để nâng quyền đều bị bỏ qua. Chỉ admin chính sửa được vai trò, staff, superuser, nhóm và quyền riêng trong `UserAdmin`. Người được ủy quyền quản lý tài khoản thường không được xem/sửa email hay đổi mật khẩu của tài khoản quản trị viên, cộng tác viên hoặc admin khác.

**Xác nhận hiện trường trước khi gửi:** `RescueCaseForm` có checkbox `location_confirmed`; `case_create` yêu cầu bắt buộc, còn form cũ giữ tùy chọn. Người báo kiểm tra địa chỉ và ghim rồi tự đánh dấu. JavaScript không đánh dấu thay người dùng, bỏ xác nhận khi dữ liệu vị trí đổi. Server từ chối tạo ca/ảnh/thông báo nếu thiếu xác nhận. Đây là xác nhận của người báo, không phải bằng chứng thiết bị đã đo đúng vị trí vật lý. Admin/người được phân công nhận đúng tọa độ lưu trong hồ sơ theo quyền; vòng sai số chỉ xuất hiện tại bước lấy vị trí trên form.
