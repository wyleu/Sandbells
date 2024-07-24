from django.contrib import admin

@admin.action(description='Build Patterms and Items for Change')
def build_items(modeladmin, request, queryset):
    for item in queryset:
        item.express()

@admin.action(description="Export MIDI")
def export_midi(modeladmin, request, queryset):
    for item in queryset:
        item.midi_file()


# Register your models here.
from .models import Pattern, Bell,  Change, ChangeItem

class PatternAdmin(admin.ModelAdmin):
    actions = [export_midi]
    list_display = ['name','number','pattern','pub_date','order','count','enable']
    readonly_fields=('number',)
    list_filter = ('number',)
    search_fields = ['name','pattern']

class BellAdmin(admin.ModelAdmin):
    list_display = ['tower','bell','weight','note',]

class ChangeAdmin(admin.ModelAdmin):
    list_display = ['from_pat','to_pat']
    actions = [build_items, export_midi]
    readonly_fields=('number',)

class ChangeItemAdmin(admin.ModelAdmin):
    list_display = ['step','change','pattern','pattern_str']

#class TowerAdmin(admin.ModelAdmin):
#    list_display = ['name',]

admin.site.register( Pattern, PatternAdmin)
#admin.site.register( Tower, TowerAdmin)
admin.site.register( Bell, BellAdmin)
admin.site.register( Change, ChangeAdmin)
admin.site.register( ChangeItem, ChangeItemAdmin)

