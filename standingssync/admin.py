from django.contrib import admin
from .models import SyncedCharacter, SyncManager, AllianceContact
from . import tasks

@admin.register(SyncedCharacter)
class SyncedCharacterAdmin(admin.ModelAdmin):
    list_display = ('user', 'character_name', 'version_hash', 'last_sync', 'last_error', 'manager')
    list_filter = ('last_error', 'version_hash', 'last_sync', 'character__user', 'manager')
    actions = ['start_sync_contacts']
    
    list_display_links = None

    def user(self, obj):
        return obj.character.user

    def character_name(self, obj):
        return obj.__str__()

    # This will help you to disbale add functionality
    def has_add_permission(self, request):
        return False

    def start_sync_contacts(self, request, queryset):
                
        names = list()
        for obj in queryset:            
            tasks.run_character_sync.delay(sync_char_pk=obj.pk, force_sync=True)
            names.append(str(obj))
    
        self.message_user(
            request, 
            'Started syncing for: {}'.format(', '.join(names))
        )
        
    start_sync_contacts.short_description = "Force sync for character"


@admin.register(SyncManager)
class SyncManagerAdmin(admin.ModelAdmin):
    list_display = (
        'alliance_name', 
        'contacts_count', 
        'user', 
        'character_name',         
        'version_hash', 
        'last_sync'
    )

    list_display_links = None

    actions = ['start_sync_managers']

    def user(self, obj):
        return obj.character.user

    def character_name(self, obj):
        return obj.__str__()

    def alliance_name(self, obj):
        return obj.character.character.alliance_name

    def contacts_count(self, obj):
        return AllianceContact.objects.filter(manager=obj).count()

    # This will help you to disbale add functionality
    def has_add_permission(self, request):
        return False

    def start_sync_managers(self, request, queryset):
                
        names = list()
        for obj in queryset:            
            tasks.run_manager_sync.delay(manager_pk=obj.pk, force_sync=True)
            names.append(str(obj))
    
        self.message_user(
            request, 
            'Started syncing for: {}'.format(', '.join(names))
        )
        
    start_sync_managers.short_description = "Force sync for managers"