from django.urls import path
from . import views

app_name = "requests"

urlpatterns = [
    path("", views.request_list, name="list"),
    path("new/", views.request_create, name="create"),
    path("<uuid:request_id>/", views.request_detail, name="detail"),
    path("<uuid:request_id>/edit/", views.request_update, name="update"),
    path("<uuid:request_id>/comments/", views.comment_add, name="comment-add"),
    path("<uuid:request_id>/assign/", views.request_assign, name="assign"),
    path("<uuid:request_id>/resolve/", views.request_resolve, name="resolve"),
]
