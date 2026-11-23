from .models import Notification


def notify(user, message, url=""):
    Notification.objects.create(user=user, message=message[:255], url=url)
