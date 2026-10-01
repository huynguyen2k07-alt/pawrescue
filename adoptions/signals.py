from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AdoptionPlacement
from .reminders import ensure_follow_up_schedule


@receiver(post_save, sender=AdoptionPlacement)
def create_adoption_follow_up_schedule(sender, instance, **kwargs):
    if instance.is_active:
        ensure_follow_up_schedule(instance)
