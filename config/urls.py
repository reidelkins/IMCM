from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

from .views import not_found, app_error

handler404 = not_found
handler500 = app_error

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/messages/', include('messages_api.urls')),
    # path('api/v1/data/', include('data.urls')),
]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)