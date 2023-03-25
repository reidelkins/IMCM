from django.urls import path, include
from rest_framework import routers
from . import views

router = routers.DefaultRouter()

urlpatterns = [
    path('recentlysold/<str:company>/', views.RecentlySoldView.as_view(), name='recently-sold'),
    path('allrecentlysold/<str:company>/', views.AllRecentlySoldView.as_view(), name='all-recently-sold'),
    path('update/<str:company>/', views.UpdateStatusView.as_view(), name='update-status'),
    path('updateclient/', views.UpdateClientView.as_view(), name='updateclient'),
    path('upload/<str:company>/', views.UploadFileView.as_view(), name='upload-file'),
    path('allClients/<str:user>/', views.AllClientListView.as_view(), name='all-client-list'),
    path('clients/<str:user>/', views.ClientListView.as_view(), name='client-list'),
    path('salesforce/<str:company>/', views.SalesforceConsumerView.as_view(), name='salesforce-consumer'),
    path('servicetitan/<str:company>/', views.ServiceTitanView.as_view(), name='servicetitian'),
]