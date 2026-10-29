"""Định tuyến URL chính, chuyển yêu cầu đến các ứng dụng của dự án."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Điều phối cứu hộ PawRescue"
admin.site.site_title = "Quản trị PawRescue"
admin.site.index_title = "Điều phối cứu hộ"
admin.site.site_url = "/"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('collaborators/', include('accounts.collaborator_urls')),
    path('accounts/', include('accounts.urls')),
    path('organizations/', include('organizations.urls')),
    path('donations/', include('donations.urls')),
    path('support/', include('support.urls')),
    path('', include('rescue.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
