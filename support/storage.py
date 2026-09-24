from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateSupportStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_SUPPORT_MEDIA_ROOT,
            base_url=None,
        )


private_support_storage = PrivateSupportStorage()
