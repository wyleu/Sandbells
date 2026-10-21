from django.contrib import admin

from .models import ChannelMap, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Read-only: events come from devices, never from the admin."""
    list_display = ("received_at", "src", "boot_id", "seq", "type", "ch",
                    "utc", "err_ms", "acc", "sync", "mode", "epoch",
                    "session", "srv", "stratum", "host")
    list_filter = ("host", "type", "src", "sync", "mode", "acc")
    search_fields = ("boot_id", "device_id")
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChannelMap)
class ChannelMapAdmin(admin.ModelAdmin):
    """Editable: which bell each device channel senses, from valid_from."""
    list_display = ("src", "ch", "bell", "valid_from", "note")
    list_filter = ("src", "bell")
    ordering = ("src", "ch", "-valid_from")
