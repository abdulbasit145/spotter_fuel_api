from django.urls import path

from api.views import RouteFuelPlanView

app_name = 'api'

urlpatterns = [
    path('route-plan/', RouteFuelPlanView.as_view(), name='route-plan'),
]
