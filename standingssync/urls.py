from django.urls import path

from . import views

app_name = "standingssync"

urlpatterns = [
    path("", views.index, name="index"),
    path("add_character", views.add_character, name="add_character"),
    path(
        "remove_character/<int:alt_pk>", views.remove_character, name="remove_character"
    ),
    path(
        "add_alliance_manager", views.add_alliance_manager, name="add_alliance_manager"
    ),
]
