import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from .reminders import dispatch_due_follow_up_reminders


logger = logging.getLogger(__name__)


class AdoptionFollowUpReminderMiddleware:
    """Dispatch due reminders periodically without requiring a task worker."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            cache_key = f"pawrescue-follow-up-reminders:{timezone.now():%Y%m%d%H%M}"
            if cache.add(cache_key, True, timeout=60):
                try:
                    dispatch_due_follow_up_reminders()
                except DatabaseError:
                    logger.exception("Unable to dispatch adoption follow-up reminders")
        return self.get_response(request)
