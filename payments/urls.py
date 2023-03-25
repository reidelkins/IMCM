from django.urls import path, include
from rest_framework import routers
from payments import views

router = routers.DefaultRouter()

urlpatterns = [
    # path('save-stripe-info/', views.save_stripe_info, name='save-stripe-info'),
    # path('setup-intent/', views.setup_intent, name='setup_intent'),
    # path('publishable-key/', views.publishable_key, name='publishable-key'),
    path("stripe/", include("djstripe.urls", namespace="djstripe")),
    path("", include(router.urls)),
]