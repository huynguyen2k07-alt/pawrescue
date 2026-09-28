from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import cached_property
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDonationStorage(FileSystemStorage):
    """Filesystem storage that deliberately has no public media URL."""

    def __init__(self):
        super().__init__(location=None, base_url=None)

    @cached_property
    def base_location(self):
        return settings.PRIVATE_DONATION_MEDIA_ROOT

    @cached_property
    def base_url(self):
        return None

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == "PRIVATE_DONATION_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)

    def url(self, name):
        raise ValueError("Private donation files do not have a public URL.")


private_donation_storage = PrivateDonationStorage()
