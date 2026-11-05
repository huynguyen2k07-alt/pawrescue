# PawRescue · Báo tin và điều phối cứu hộ

Website Django cho phép người dùng báo ca động vật cần cứu hộ tại Đà Nẵng. **Admin chính** điều phối và duyệt kết quả; **quản trị viên cứu hộ** (`moderator`) kiểm tra những ca được giao. Chỉ admin chính được tạo/cấp quyền quản trị viên hoặc quyền admin; đăng ký công khai luôn tạo người dùng thường. Tính năng nhận nuôi hiện đã tắt.

Luồng chính: người dùng báo tin → admin chính bấm **Gửi ca cho các quản trị viên** → quản trị viên xác nhận thông tin hoặc từ chối tin không hợp lệ → sau cứu hộ, quản trị viên **Báo đã hoàn thành** → admin chính **Duyệt thành công và công khai**. Việc giao ca tạo phân công và tin riêng nhưng vẫn giữ tin mới ở `reported`; ca chỉ chuyển sang `verified` sau khi được xác minh.

Khi báo ca thiếu thông tin hoặc chưa xác nhận ghim, form ghi rõ **Chưa gửi được báo cáo tới admin**, liệt kê lỗi và đưa con trỏ tới mục đầu tiên cần sửa; chưa tạo hồ sơ hay thông báo. Gửi thành công mới chuyển sang trang chi tiết và hiện **Mã tin báo: #…**. Nếu vẫn ở form, sửa các mục báo lỗi rồi gửi lại; admin chỉ nhận các ca đã được lưu hợp lệ.

Quản trị viên có khu vực ca được giao tại `/collaborators/`, không có quyền quản trị tài khoản, quỹ, tổ chức hoặc hộp thư hỗ trợ chung. Báo hoàn thành yêu cầu đánh giá cùng địa chỉ/tọa độ Đà Nẵng hợp lệ; trạng thái `pending_review` lưu người báo kết quả, ghi chú và thời điểm, chờ admin chính duyệt. Khi chờ duyệt, quản trị viên không sửa kết quả, từ chối hoặc cập nhật hiện trường. Từ chối tin báo là thao tác xóa thật, có trang xác nhận và lý do; thông báo cho admin chính và người báo tin được giữ lại sau xóa.

Bản đồ công khai `/map/` chỉ lưu điểm đã được admin chính duyệt thành công (`rescued`), kể cả khi admin xem trang này. Ca `pending_review` chưa xuất hiện trên bản đồ. Bản đồ nhỏ trong hồ sơ phục vụ điều phối theo quyền; nút mở Google Maps dùng chính tọa độ được phép hiển thị, nên vị trí riêng tư vẫn được làm gần đúng với người ngoài. Đây là liên kết xem bản đồ, không đăng địa điểm lên Google Maps.

Báo ca dùng một bản đồ ngay trong website: nhập **Địa chỉ cụ thể / mốc nhận biết** → bấm **Tìm địa chỉ trên bản đồ** → chọn gợi ý → kiểm tra/kéo ghim → tự đánh dấu xác nhận → gửi tin. Geoapify chỉ gợi ý vị trí; chọn gợi ý giữ nguyên địa chỉ và mốc người báo đã nhập, không tự đánh dấu xác nhận. Tìm kiếm chỉ chạy khi bấm nút, không gọi theo từng ký tự. Người báo cũng có thể bấm **Dùng vị trí hiện tại** hoặc bấm trực tiếp trên bản đồ; ô tọa độ thủ công được thu gọn để dùng khi cần. Website tự chọn nền mặc định và chuyển nền dự phòng nếu lỗi. Leaflet được lưu cùng website tại `static/vendor/leaflet/`; ảnh nền cần mạng. Bấm ghim ca thành công để xem ảnh, địa chỉ theo quyền, đơn vị cứu hộ, thời điểm admin duyệt và liên kết mở hồ sơ.

Nút lấy vị trí chỉ cần bấm một lần: hiện ghim ngay khi thiết bị trả tọa độ đủ dùng, luôn ghi sai số ước tính và chỉ tự thay ghim khi có kết quả chính xác hơn. Nếu sai số trên 1.000 m, form hiển thị dấu hỏi màu xám kèm vòng sai số, ghi rõ chưa chọn hiện trường; kéo ghim hoặc bấm bản đồ mới chọn tọa độ, không tự ghi đè điểm đã chọn. Trước khi gửi, người báo phải đánh dấu đã kiểm tra ghim và địa chỉ đúng hiện trường. Đổi địa chỉ/ghim/tọa độ hoặc lấy GPS lại sẽ bỏ dấu xác nhận cũ; server cũng chặn tin thiếu xác nhận. Chờ cấp quyền tối đa 30 giây; sau khi có quyền/dữ liệu, dành tối đa 15 giây lấy và cải thiện vị trí. Tự dừng khi đạt sai số tối đa 50 m hoặc hết chờ, khi hủy, chọn ghim thủ công, ẩn tab hay rời trang. Khi cả hai lượt lấy vị trí đều báo lỗi, dừng ngay và phân biệt không có dịch vụ vị trí, hết thời gian hoặc bị chặn quyền. Khởi tạo bản đồ lỗi vẫn lấy/nhập tọa độ được. Trên laptop, trình duyệt có thể chỉ trả vị trí gần đúng; website không bảo đảm định vị tức thì hoặc chính xác tuyệt đối. Không dùng DNS/IP để giả làm vị trí hiện trường.

Trang chủ có cẩm nang, giới thiệu đội ngũ, góp ý, thông tin ủng hộ và hai biểu đồ công khai. Danh sách tách **Chờ xác nhận** (`reported`) khỏi **Đã phê duyệt** (`verified`, `assigned`, `in_progress`, `pending_review`); hai mục không chứa cùng một ca. Mặc định mở mục đã phê duyệt; tin chờ xác nhận vẫn chỉ người liên quan được xem. Ca `closed` được gộp với `cancelled` ở mục đã hủy.

`rescue/statistics.py` dùng Pandas tổng hợp chuỗi ngày, NumPy tính số liệu và Matplotlib vẽ ảnh biểu đồ. Biểu đồ trạng thái và bảng số liệu chỉ có ba nhóm: **Đã xác nhận** (hệ thống đã nhận request, chưa chốt kết quả), **Đã cứu thành công**, **Đã hủy** (gồm hồ sơ đóng không thành công). Chỉ đếm số lượng/ngày nhận, kể cả request mới chưa duyệt; không công khai nội dung, địa chỉ hoặc liên hệ của tin chưa duyệt. Biểu đồ ngày đếm request nhận trong bảy ngày; bản đồ tổng hợp vẫn chỉ hiển thị `rescued`. Thông tin ngân hàng cuối trang lấy từ chiến dịch đang hoạt động của tổ chức đã xác minh, có đủ ngân hàng, chủ tài khoản và số tài khoản.

Biểu đồ tự kiểm tra dữ liệu mới mỗi 5 giây khi đang xem trang, không cần tải lại. Qua 0 giờ theo múi giờ website, khung 7 ngày tự thêm ngày mới và bỏ ngày cũ nhất. Khi ẩn tab hoặc mất mạng, phần cập nhật tạm dừng rồi tự tiếp tục. Endpoint chỉ đọc `/statistics/live/` dùng mã phiên bản để không tải lại hai ảnh khi số liệu không đổi.

Chuông thông báo và notice mới tự cập nhật khoảng **2 giây** trên mọi trang đã đăng nhập, bao gồm Django admin. Khi có thông báo từ cứu hộ, nhắn tin, góp ý hoặc đóng góp, giao diện cập nhật số chưa đọc và hiện notice có liên kết; không tải lại trang đang nhập liệu. Chỉ lấy thông báo tài khoản đang đăng nhập được phép xem. Ẩn tab hoặc mất mạng thì tạm dừng, quay lại tự đồng bộ; mất phiên thì dừng nhận dữ liệu. Endpoint chỉ đọc là `/notifications/state/`; đọc thông báo vẫn dùng POST có CSRF. Nút **Đánh dấu đã đọc** và **Đánh dấu tất cả đã đọc** cập nhật ngay tại danh sách, giữ nguyên trang và vị trí cuộn; **Xem nội dung** là liên kết mở nội dung riêng.

## Chạy server trên máy hiện tại

Mở terminal trong thư mục dự án rồi chạy:

```bash
cd /home/huy/animal-rescue
source .venv/bin/activate
python manage.py runserver
```

Giữ terminal mở khi dùng website. Truy cập [trang chủ](http://127.0.0.1:8000/), [báo ca mới](http://127.0.0.1:8000/cases/new/), [bản đồ ca đã cứu thành công](http://127.0.0.1:8000/map/) hoặc [admin](http://localhost:8000/admin/). Nhấn `Ctrl+C` trong terminal để dừng server.

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

Nếu vừa clone dự án sang máy mới, sao chép `.env.example` thành `.env` rồi điền cấu hình PostgreSQL và secret riêng trước khi chạy migration. Không ghi đè `.env` đã có. GitHub chỉ lưu file cấu hình mẫu, không lưu tài khoản/mật khẩu hay dữ liệu trong CSDL trên máy đang phát triển.

Muốn tạo tài khoản admin mới trên một môi trường mới, dùng `python manage.py createsuperuser`. Tài khoản đăng ký qua website là tài khoản người dùng thông thường.

## Bật tìm địa chỉ Geoapify

Lưu khóa của dự án trong `.env` bằng biến `GEOAPIFY_API_KEY`; không đưa khóa vào mã nguồn, HTML, JavaScript, ảnh chụp hoặc báo cáo. Ví dụ dưới đây chỉ là chỗ giữ để thay bằng khóa riêng trên máy:

```dotenv
GEOAPIFY_API_KEY=dan_key_cua_ban_vao_day
```

Có thể cần khởi động lại server sau khi đổi `.env`. Thiếu khóa thì form ẩn nút tìm địa chỉ; chọn ghim, lấy vị trí thiết bị và nhập tọa độ vẫn dùng được. `config/settings.py` đọc khóa phía máy chủ. Trình duyệt gửi địa chỉ qua **POST `/locations/search/`**, yêu cầu đăng nhập và CSRF; `rescue/geocoding.py` mới gọi Geoapify. Khóa không được gửi xuống trình duyệt. Tìm kiếm không tạo hồ sơ cứu hộ hoặc thông báo; chỉ nút gửi tin mới lưu báo cáo hợp lệ.

Kết quả tìm giới hạn trong vùng tiếp nhận Đà Nẵng của dự án: vĩ độ `15.85–16.25`, kinh độ `107.75–108.35`, tối đa năm gợi ý. Địa chỉ tìm được gửi tới Geoapify; form có liên kết ghi nguồn dịch vụ. Gợi ý có thể chưa đúng số nhà hoặc hiện trường, và không tăng độ chính xác GPS trên laptop. Nếu dịch vụ lỗi, hết thời gian hoặc hết quota, người báo vẫn chọn ghim/nhập tọa độ, kiểm tra địa chỉ và tự xác nhận để gửi tin.

Theo thông tin gói Free tại thời điểm tra cứu **02/11/2026**, Geoapify cung cấp **3.000 credits/ngày**, có yêu cầu giữ liên kết ghi nguồn (attribution) và giới hạn sử dụng. Xem [bảng giá Geoapify](https://www.geoapify.com/pricing/) trước khi triển khai; hạn mức và điều kiện có thể thay đổi. Ứng dụng dùng cache kết quả một giờ và giới hạn lượt gọi để giảm tiêu hao quota. Cache mặc định chỉ dùng chung trong từng process; triển khai nhiều worker cần cache dùng chung để áp dụng giới hạn tổng.

## Đọc và sửa code

Chú thích tiếng Việt được đánh dấu bằng tiêu đề `===== CHỨC NĂNG CHÍNH: ... =====` ở các phần cần học. Xem [lộ trình học và trình bày đồ án](docs/HUONG_DAN_DOC_CODE.md) để đi từ URL → form → view → model → giao diện, rồi theo dõi luồng báo ca, bản đồ, phân quyền, phân công và admin chốt kết quả.

[Danh sách chú thích](docs/DANH_SACH_CHU_THICH.md) liệt kê từng vị trí đã ghi chú, tên hàm và tác dụng của đoạn code để tra cứu khi trình bày.

[Checklist tự kiểm thử và pentest](docs/CHECKLIST_KIEM_THU_VA_PENTEST.md) liệt kê thao tác thử, kết quả mong đợi và các URL còn hoạt động, kể cả chức năng đã ẩn khỏi menu.

Các file trong `.venv/` là thư viện cài đặt; `media/` và `private_media/` chứa tệp người dùng tải lên; `output/` chứa kết quả kiểm thử. Đây không phải nơi sửa chức năng của website.

## Kiểm tra sau khi sửa

```bash
# Kiểm tra cấu hình Django.
.venv/bin/python manage.py check --settings=config.test_settings

# Chạy bộ kiểm thử Python trong SQLite tách biệt dữ liệu thật.
.venv/bin/python manage.py test --settings=config.test_settings --noinput

# Kiểm tra bản đồ, định vị, tìm địa chỉ, thông báo, chat và biểu đồ.
node --test --test-isolation=none tests/*.test.cjs
```

Muốn kiểm thử với PostgreSQL đang cấu hình, chạy `.venv/bin/python scripts/run_postgres_audit.py`. Script tạo schema kiểm thử riêng, chạy migration và kiểm thử trong schema đó rồi xóa schema khi kết thúc. Nó cần quyền tạo schema trong database.

Xem [tóm tắt kiểm thử các vai trò và chức năng](docs/KIEM_THU.md). Báo cáo chi tiết, log và dữ liệu QA trong `output/` được giữ trên máy kiểm thử, không đưa lên GitHub.

Xem [hướng dẫn Geoapify và tùy chọn Google Maps](docs/GOOGLE_MAPS_SETUP.md). Website hiện tìm địa chỉ bằng Geoapify và hiển thị bản đồ Leaflet/OpenStreetMap; Google Maps Platform chưa được tích hợp.
