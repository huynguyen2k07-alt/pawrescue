from django.core.management.base import BaseCommand
from django.db import transaction

from rescue.models import ContributorProfile, KnowledgeArticle


CONTRIBUTORS = (
    {
        "name": "Nhóm điều phối hiện trường",
        "role": "Tiếp nhận & xác minh",
        "bio": (
            "Kết nối người báo tin với tổ chức phù hợp, kiểm tra thông tin "
            "và ưu tiên những trường hợp khẩn cấp."
        ),
        "static_image_path": "images/community/volunteer-dogs.jpg",
        "photo_credit": "Mia X / Pexels",
        "photo_source_url": (
            "https://www.pexels.com/photo/volunteer-feeding-rescued-dogs-at-"
            "animal-shelter-35231857/"
        ),
        "display_order": 1,
        "is_active": True,
    },
    {
        "name": "Nhóm chăm sóc tạm thời",
        "role": "Foster & phục hồi",
        "bio": (
            "Hỗ trợ nơi ở tạm, theo dõi sức khỏe và giúp động vật làm quen "
            "lại với một môi trường an toàn."
        ),
        "static_image_path": "images/community/shelter-cat.jpg",
        "photo_credit": "Artem Kniaz / Unsplash",
        "photo_source_url": (
            "https://unsplash.com/photos/a-cat-is-sitting-inside-of-a-small-"
            "window-AA0mTuZtGsw"
        ),
        "display_order": 2,
        "is_active": True,
    },
    {
        "name": "Nhóm truyền thông cộng đồng",
        "role": "Kiến thức & kết nối",
        "bio": (
            "Biên soạn kiến thức dễ hiểu, lan tỏa các ca cần giúp và xây "
            "dựng một cộng đồng cứu hộ có trách nhiệm."
        ),
        "static_image_path": "images/community/kitten-shelter.jpg",
        "photo_credit": "Eleni Trapp / Unsplash",
        "photo_source_url": (
            "https://unsplash.com/photos/a-tabby-kitten-reaches-for-a-latch-"
            "on-a-cage-x6Mx2mTY-1Y"
        ),
        "display_order": 3,
        "is_active": True,
    },
)


ARTICLES = (
    {
        "title": "Gặp động vật bị thương: 5 bước an toàn đầu tiên",
        "slug": "gap-dong-vat-bi-thuong-5-buoc-an-toan",
        "category": KnowledgeArticle.Category.RESCUE,
        "excerpt": (
            "Giữ khoảng cách, ghi lại vị trí và gọi đúng người hỗ trợ trước "
            "khi chạm vào động vật đang hoảng sợ."
        ),
        "body": """1. Quan sát từ khoảng cách an toàn

Động vật bị đau có thể cắn hoặc cào dù bình thường rất hiền. Trước tiên hãy kiểm tra giao thông, dây điện, nước sâu và những nguy hiểm quanh hiện trường.

2. Ghi lại vị trí chính xác

Lưu địa chỉ, mốc dễ nhận biết hoặc ghim tọa độ. Nếu con vật di chuyển, hãy ghi lại hướng đi thay vì đuổi theo.

3. Giữ trẻ em và thú nuôi ở xa

Tạo một khoảng trống yên tĩnh để giảm căng thẳng. Không tụ tập, chiếu đèn mạnh hoặc cố cho ăn khi chưa biết tình trạng.

4. Chỉ di chuyển khi thật sự cần thiết

Với con vật nhỏ, có thể dùng khăn dày và hộp thông khí nếu việc tiếp cận an toàn. Không tự bắt động vật lớn, hung dữ hoặc động vật hoang dã có khả năng gây nguy hiểm.

5. Liên hệ bác sĩ thú y hoặc đội cứu hộ

Mô tả loài, kích thước, dấu hiệu chấn thương và vị trí. Làm theo hướng dẫn của người có chuyên môn trong lúc chờ hỗ trợ.""",
        "static_image_path": "images/community/vet-kitten.jpg",
        "image_credit": "Judy Beth Morris / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/a-white-kitten-being-examined-by-a-"
            "veterinator-5Bi6MWlWMbw"
        ),
        "source_name": "RSPCA — Injured wild animals",
        "source_url": "https://www.rspca.org.uk/adviceandwelfare/wildlife/injured",
        "is_featured": True,
        "is_published": True,
    },
    {
        "title": "Nhận biết và sơ cứu sốc nhiệt ở chó mèo",
        "slug": "nhan-biet-va-so-cuu-soc-nhiet-cho-meo",
        "category": KnowledgeArticle.Category.HEALTH,
        "excerpt": (
            "Thở gấp, chảy dãi, lừ đừ hoặc mất thăng bằng có thể là cấp "
            "cứu. Làm mát đúng cách và gọi bác sĩ thú y ngay."
        ),
        "body": """Sốc nhiệt là một tình trạng cấp cứu

Các dấu hiệu có thể gồm thở gấp bất thường, chảy nhiều dãi, lợi đỏ hoặc nhợt, nôn, yếu, lú lẫn, mất thăng bằng hay co giật. Đừng chờ các dấu hiệu tự hết.

Đưa con vật ra khỏi nguồn nóng

Chuyển ngay tới nơi râm mát hoặc phòng thông thoáng. Tạo luồng gió bằng quạt hay điều hòa nếu có.

Bắt đầu làm mát

Dùng nước máy mát dội hoặc thấm lên cơ thể, tránh để nước đi vào mũi và miệng. Không trùm kín bằng khăn ướt vì khăn có thể giữ nhiệt. Cho uống từng ít nước nếu con vật tỉnh táo nhưng không ép uống.

Liên hệ bác sĩ thú y ngay

Gọi cơ sở thú y trong lúc bắt đầu làm mát và làm theo chỉ dẫn. Ngay cả khi có vẻ hồi phục, con vật vẫn cần được kiểm tra vì tổn thương bên trong có thể xuất hiện muộn.""",
        "static_image_path": "images/community/dog-cooling.jpg",
        "image_credit": "Lucie Hošová / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/dog-happily-cooling-off-in-the-water-"
            "5c8BlnGwmDI"
        ),
        "source_name": "PDSA — First aid for heatstroke",
        "source_url": (
            "https://www.pdsa.org.uk/pet-help-and-advice/pet-health-hub/"
            "other-veterinary-advice/first-aid-for-heatstroke"
        ),
        "is_featured": False,
        "is_published": True,
    },
    {
        "title": "Chuẩn bị một hộp cứu hộ động vật cơ bản",
        "slug": "chuan-bi-hop-cuu-ho-dong-vat-co-ban",
        "category": KnowledgeArticle.Category.CARE,
        "excerpt": (
            "Hộp thoáng khí, khăn dày, găng tay và danh bạ hỗ trợ giúp bạn "
            "ứng phó bình tĩnh hơn khi gặp một ca cần cứu."
        ),
        "body": """Những vật dụng nên có

Chuẩn bị hộp hoặc lồng vận chuyển chắc chắn có lỗ thông khí, khăn dày, găng tay bảo hộ, đèn pin, túi rác, nước sạch và giấy để ghi thông tin. Không để thuốc của người trong hộp cứu hộ động vật.

Thông tin quan trọng không nên thiếu

Lưu sẵn số điện thoại bác sĩ thú y gần nhất, tổ chức cứu hộ địa phương và cơ quan phụ trách động vật hoang dã. Ghi lại vị trí chính xác nơi tìm thấy con vật.

Dùng hộp thế nào cho an toàn

Lót khăn, giữ hộp ở nơi tối, yên tĩnh và thông thoáng. Hạn chế mở hộp hoặc kiểm tra liên tục. Không tự cho ăn hay uống nếu chưa được người có chuyên môn hướng dẫn.

Biết giới hạn của mình

Bộ dụng cụ giúp hỗ trợ ban đầu, không thay thế chuyên gia bắt giữ. Với động vật lớn, hung dữ, có nọc độc hoặc dấu hiệu bệnh truyền nhiễm, hãy giữ khoảng cách và gọi lực lượng phù hợp.""",
        "static_image_path": "images/community/dog-water.jpg",
        "image_credit": "R_ INVSCIMENTO / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/a-dog-is-standing-in-the-cool-water-"
            "dZOn8GQ0jpU"
        ),
        "source_name": "Ready.gov — Pets and Animals",
        "source_url": "https://www.ready.gov/pets",
        "is_featured": False,
        "is_published": True,
    },
    {
        "title": "Thấy mèo con ngoài đường: khi nào nên can thiệp?",
        "slug": "thay-meo-con-ngoai-duong-khi-nao-nen-can-thiep",
        "category": KnowledgeArticle.Category.RESCUE,
        "excerpt": (
            "Mèo mẹ có thể chỉ đang đi kiếm thức ăn. Quan sát đúng cách giúp "
            "tránh tách mèo con khỏe mạnh khỏi mẹ quá sớm."
        ),
        "body": """Quan sát trước khi đưa mèo con đi

Nếu khu vực an toàn, hãy lùi xa và quan sát trong vài giờ. Mèo mẹ thường tránh xuất hiện khi có người đứng gần, nhưng có thể quay lại để cho con bú.

Đánh giá tình trạng

Mèo con sạch, ấm, nằm yên và bụng tròn thường đang được mẹ chăm. Cần hỗ trợ sớm nếu các bé lạnh, ướt, kêu liên tục, bị thương, quá gầy hoặc đang ở nơi có xe cộ và nguy hiểm trực tiếp.

Khi phải di chuyển

Giữ ấm bằng khăn khô và nguồn nhiệt được bọc kỹ; không đặt nhiệt trực tiếp lên da. Không cho mèo con đang lạnh ăn. Liên hệ bác sĩ thú y hoặc người có kinh nghiệm chăm mèo sơ sinh để được hướng dẫn.

Nếu mẹ vẫn chăm con

Có thể hỗ trợ nước, thức ăn và một chỗ trú khô cho mèo mẹ ở gần vị trí cũ. Theo dõi từ xa và lên kế hoạch triệt sản khi phù hợp.""",
        "static_image_path": "images/community/kitten-shelter.jpg",
        "image_credit": "Eleni Trapp / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/a-tabby-kitten-reaches-for-a-latch-"
            "on-a-cage-x6Mx2mTY-1Y"
        ),
        "source_name": "Alley Cat Allies — Finding Kittens Outdoors",
        "source_url": (
            "https://www.alleycat.org/community-cat-care/finding-kittens-outdoors/"
        ),
        "is_featured": False,
        "is_published": True,
    },
    {
        "title": "Tiếp cận chó lạ mà không làm chúng hoảng sợ",
        "slug": "tiep-can-cho-la-an-toan",
        "category": KnowledgeArticle.Category.RESCUE,
        "excerpt": (
            "Đứng nghiêng, tránh nhìn chằm chằm và để chó chủ động rút ngắn "
            "khoảng cách là những nguyên tắc quan trọng."
        ),
        "body": """Đọc tín hiệu trước khi tiến lại

Không tiến gần nếu chó gầm, nhe răng, cứng người, dựng lông, cụp đuôi sát bụng hoặc liên tục tìm đường chạy. Hãy tạo khoảng cách và gọi người có chuyên môn.

Giảm áp lực

Đứng hơi nghiêng, tránh cúi phủ người hoặc nhìn thẳng vào mắt. Không chạy theo, dồn vào góc hay đưa tay sát mặt chó. Nói nhỏ và di chuyển chậm.

Để chó có quyền lựa chọn

Nếu môi trường an toàn, đứng yên và để chó tự đến ngửi. Trẻ em không nên tự tiếp cận chó lạ. Giữ thú cưng của bạn ở xa để tránh xung đột.

Khi có nguy cơ bị cắn

Không la hét hoặc bỏ chạy. Dùng vật cản như balô hay ghế để tạo khoảng cách và từ từ lùi ra. Nếu bị cắn, rửa vết thương và tìm tư vấn y tế sớm.""",
        "static_image_path": "images/community/volunteer-dogs.jpg",
        "image_credit": "Mia X / Pexels",
        "image_source_url": (
            "https://www.pexels.com/photo/volunteer-feeding-rescued-dogs-at-"
            "animal-shelter-35231857/"
        ),
        "source_name": "AVMA — Dog bite prevention",
        "source_url": (
            "https://www.avma.org/resources-tools/pet-owners/dog-bite-prevention"
        ),
        "is_featured": False,
        "is_published": True,
    },
    {
        "title": "Kế hoạch khẩn cấp cho gia đình có thú cưng",
        "slug": "ke-hoach-khan-cap-cho-gia-dinh-co-thu-cung",
        "category": KnowledgeArticle.Category.CARE,
        "excerpt": (
            "Chuẩn bị lồng vận chuyển, hồ sơ sức khỏe và người liên hệ dự "
            "phòng trước mùa mưa bão giúp cả nhà rời đi an toàn hơn."
        ),
        "body": """Lập kế hoạch trước khi có sự cố

Xác định nơi trú tạm chấp nhận động vật và ít nhất hai tuyến đường rời nhà. Thống nhất người sẽ phụ trách từng con vật nếu gia đình không ở cùng nhau.

Chuẩn bị túi đồ riêng

Đặt sẵn thức ăn, nước, bát, thuốc đang dùng, dây dắt, túi vệ sinh, ảnh nhận dạng và bản sao hồ sơ thú y trong túi chống ẩm. Lồng vận chuyển nên vừa vặn và có ghi thông tin liên hệ.

Giữ thông tin nhận dạng cập nhật

Kiểm tra thẻ tên và số điện thoại. Lưu một ảnh gần đây của bạn cùng thú cưng để hỗ trợ chứng minh quyền sở hữu nếu bị thất lạc.

Luyện tập nhẹ nhàng

Cho thú cưng làm quen với lồng vận chuyển và thử quy trình rời nhà. Việc luyện tập ngắn, tích cực sẽ giảm căng thẳng khi thật sự cần sơ tán.""",
        "static_image_path": "images/community/shelter-cat.jpg",
        "image_credit": "Artem Kniaz / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/a-cat-is-sitting-inside-of-a-small-"
            "window-AA0mTuZtGsw"
        ),
        "source_name": "Ready.gov — Pets and Animals",
        "source_url": "https://www.ready.gov/pets",
        "is_featured": False,
        "is_published": True,
    },
    {
        "title": "Những thực phẩm trong nhà không nên cho chó mèo ăn",
        "slug": "thuc-pham-khong-nen-cho-cho-meo-an",
        "category": KnowledgeArticle.Category.HEALTH,
        "excerpt": (
            "Chocolate, nho, hành tỏi và sản phẩm có xylitol có thể gây nguy "
            "hiểm; đừng tự gây nôn khi chưa được hướng dẫn."
        ),
        "body": """Phòng ngừa bắt đầu từ cách cất giữ

Chocolate, nho và nho khô, hành tỏi, đồ uống có cồn, caffeine và sản phẩm chứa xylitol là những ví dụ có thể gây hại. Mức độ nguy hiểm phụ thuộc loài, lượng ăn và tình trạng sức khỏe.

Nếu nghi thú cưng ăn nhầm

Giữ lại bao bì, ước tính lượng và thời điểm đã ăn, sau đó gọi bác sĩ thú y ngay. Không chờ xuất hiện triệu chứng mới tìm trợ giúp.

Không tự xử lý theo mẹo truyền miệng

Không tự gây nôn, cho uống sữa, dầu hay thuốc của người nếu bác sĩ thú y chưa hướng dẫn. Một số cách xử lý có thể làm tình trạng nặng hơn.

Tạo thói quen an toàn

Đậy kín thùng rác, để thuốc và thức ăn ngoài tầm với, đồng thời nhắc trẻ em và khách đến nhà không tự ý cho thú cưng ăn.""",
        "static_image_path": "images/community/vet-kitten.jpg",
        "image_credit": "Judy Beth Morris / Unsplash",
        "image_source_url": (
            "https://unsplash.com/photos/a-white-kitten-being-examined-by-a-"
            "veterinator-5Bi6MWlWMbw"
        ),
        "source_name": "ASPCA — People Foods to Avoid Feeding Your Pets",
        "source_url": (
            "https://www.aspca.org/pet-care/animal-poison-control/people-foods-"
            "avoid-feeding-your-pets"
        ),
        "is_featured": False,
        "is_published": True,
    },
)


class Command(BaseCommand):
    help = "Tạo hoặc cập nhật nội dung mẫu công khai của PawRescue."

    @transaction.atomic
    def handle(self, *args, **options):
        contributor_created = 0
        article_created = 0

        for contributor in CONTRIBUTORS:
            _profile, created = ContributorProfile.objects.update_or_create(
                name=contributor["name"],
                defaults=contributor,
            )
            contributor_created += int(created)

        for article in ARTICLES:
            _article, created = KnowledgeArticle.objects.update_or_create(
                slug=article["slug"],
                defaults=article,
            )
            article_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                "Đã đồng bộ "
                f"{len(CONTRIBUTORS)} cộng tác viên "
                f"({contributor_created} mới) và "
                f"{len(ARTICLES)} bài kiến thức ({article_created} mới)."
            )
        )
