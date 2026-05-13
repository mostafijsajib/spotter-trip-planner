from django.urls import path
from . import views

urlpatterns = [
    path('calculate/', views.calculate_trip, name='calculate_trip'),
]