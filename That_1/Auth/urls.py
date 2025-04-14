from django.urls import path
from . import views

urlpatterns = [
    path("auth/signup/", views.signup, name='signup'),
    # path("auth/create_user/", views.create_user, name='create_user')
]