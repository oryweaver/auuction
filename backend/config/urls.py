from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static


def health(_):
    return HttpResponse('ok')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health),
    path('', include('auctions.urls', namespace='auctions')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
