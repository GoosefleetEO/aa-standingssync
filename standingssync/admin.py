from django.contrib import admin
from django.db.models import Prefetch
from django.utils.html import format_html

from . import tasks
from .models import EveContact, EveEntity, EveWar, SyncedCharacter, SyncManager


@admin.register(EveContact)
class EveContactAdmin(admin.ModelAdmin):
    list_display = ("_entity_id", "_entity_category", "standing", "is_war_target")
    list_display_links = None
    ordering = ("eve_entity_id",)
    list_select_related = True
    list_filter = ("eve_entity__category", "is_war_target")

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        return False

    @admin.display(ordering="eve_entity_id")
    def _entity_id(self, obj):
        return obj.eve_entity_id

    @admin.display(ordering="eve_entity__category")
    def _entity_category(self, obj):
        return obj.eve_entity.get_category_display()


class ActiveWarsListFilter(admin.SimpleListFilter):
    title = "active_wars"
    parameter_name = "active_wars"

    def lookups(self, request, model_admin):
        return (
            ("yes", "yes"),
            ("no", "no"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.annotate_active_wars().filter(active=True)
        if self.value() == "no":
            return queryset.annotate_active_wars().filter(active=False)
        return queryset


class AlliesInline(admin.TabularInline):
    model = EveWar.allies.through


@admin.register(EveWar)
class EveWarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "declared",
        "aggressor",
        "defender",
        "_allies",
        "started",
        "finished",
        "_active",
    )
    ordering = ("-declared",)
    list_filter = ("declared", ActiveWarsListFilter)
    search_fields = ("aggressor__id", "defender__id", "allies__id")
    inlines = (AlliesInline,)

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            Prefetch("allies", queryset=EveEntity.objects.select_related())
        ).annotate_active_wars()

    @admin.display(boolean=True, ordering="active")
    def _active(self, obj) -> bool:
        return obj.active

    @admin.display()
    def _allies(self, obj):
        allies = sorted([str(ally) for ally in obj.allies.all()])
        return format_html("<br>".join(allies)) if allies else "-"


@admin.register(SyncedCharacter)
class SyncedCharacterAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "character_name",
        "version_hash",
        "_sync_ok",
        "last_sync",
        "last_error",
        "manager",
    )
    list_filter = (
        "last_error",
        "version_hash",
        "last_sync",
        "character_ownership__user",
        "manager",
    )
    actions = ["start_sync_contacts"]
    list_display_links = None

    @admin.display(boolean=True)
    def _sync_ok(self, obj) -> bool:
        return obj.is_sync_ok

    def has_add_permission(self, request):
        return False

    def user(self, obj):
        return obj.character_ownership.user

    def character_name(self, obj):
        return obj.__str__()

    @admin.display(description="Sync selected characters")
    def start_sync_contacts(self, request, queryset):
        names = list()
        for obj in queryset:
            tasks.run_character_sync.delay(sync_char_pk=obj.pk, force_sync=True)
            names.append(str(obj))
        self.message_user(request, "Started syncing for: {}".format(", ".join(names)))


@admin.register(SyncManager)
class SyncManagerAdmin(admin.ModelAdmin):
    list_display = (
        "alliance_name",
        "contacts_count",
        "synced_characters_count",
        "user",
        "character_name",
        "version_hash",
        "_sync_ok",
        "last_sync",
        "last_error",
    )
    list_display_links = None
    actions = ["start_sync_managers"]

    @admin.display(boolean=True)
    def _sync_ok(self, obj) -> bool:
        return obj.is_sync_ok

    def has_add_permission(self, request):
        return False

    def user(self, obj):
        return obj.character_ownership.user if obj.character_ownership else None

    def character_name(self, obj):
        return obj.__str__()

    def alliance_name(self, obj):
        return obj.alliance.alliance_name

    def contacts_count(self, obj):
        return "{:,}".format(obj.contacts.count())

    def synced_characters_count(self, obj):
        return "{:,}".format(obj.synced_characters.count())

    @admin.display(description="Sync selected managers")
    def start_sync_managers(self, request, queryset):
        names = list()
        for obj in queryset:
            tasks.run_manager_sync.delay(manager_pk=obj.pk, force_sync=True)
            names.append(str(obj))
        text = "Started syncing for: {} ".format(", ".join(names))
        self.message_user(request, text)
