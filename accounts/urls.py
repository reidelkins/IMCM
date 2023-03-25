from django.urls import path, include
from rest_framework import routers
from . import views

from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet)

# login_patterns = [
#     path('', views.MyTokenObtainPairView.as_view(), name='login'),
# ]

urlpatterns = [
    path('verify_registration/', views.VerifyRegistrationView.as_view(), name='verify'),
    path('confirmation/<str:pk>/<str:uid>/', views.confirmation, name='email_confirmation'),
    path('otp/disable/', views.OTPDisableView.as_view(), name='otp-disable'),
    path('otp/validate/', views.OTPValidateView.as_view(), name='otp-validate'),
    path('otp/verify/', views.OTPVerifyView.as_view(), name='otp-verify'),
    path('otp/generate/', views.OTPGenerateView.as_view(), name='otp-generate'),
    # path('company/', views.company, name='createCompany'),
    path('manageuser/<str:id>/', views.ManageUserView.as_view(), name='manageuser'),    
    path('password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    path('users/<str:company>/', views.UserListView.as_view(), name='user-list'),
    path('register/', views.RegisterView.as_view(), name='register'),
    # path('login/', include(login_patterns)),
    path('authenticated_user/<str:email>/', views.AuthenticatedUserView.as_view(), name='authenticated_user'),
    path("", include(router.urls)),
    
]
