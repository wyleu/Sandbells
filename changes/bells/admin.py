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



# Chimes: handbell tune sheets.  Upload a PDF or an image; the page images are
# made on save (bells/chimes.py).
from django import forms
from django.contrib import messages
from django.urls import reverse
from django.utils.html import format_html

from . import chimes as chime_files
from .models import ChimeTune, ChimePage


class ChimeTuneForm(forms.ModelForm):
    class Meta:
        model = ChimeTune
        fields = "__all__"

    def clean_source(self):
        source = self.cleaned_data.get("source")
        name = getattr(source, "name", "") or ""
        kind = chime_files.source_kind(name)
        if source and not kind:
            raise forms.ValidationError("Use a PDF or an image (%s)."
                                        % ", ".join(chime_files.ALLOWED_EXTENSIONS))
        if kind == "pdf" and not chime_files.pdftoppm_path():
            raise forms.ValidationError(chime_files.MISSING_POPPLER_MESSAGE)
        return source


class ChimePageInline(admin.TabularInline):
    model = ChimePage
    extra = 0
    can_delete = False
    fields = ("number", "width", "height", "preview")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Page")
    def preview(self, page):
        if not page.pk:
            return ""
        url = reverse("chime_page", args=[page.tune.slug, page.number])
        return format_html('<a href="{}" target="_blank">open</a>', url)


@admin.action(description="Re-make page images")
def rerender_chimes(modeladmin, request, queryset):
    for tune in queryset:
        try:
            tune.render_pages(force=True)
        except chime_files.ChimeRenderError as e:
            modeladmin.message_user(request, "%s: %s" % (tune, e), messages.ERROR)


class ChimeTuneAdmin(admin.ModelAdmin):
    form = ChimeTuneForm
    actions = [rerender_chimes]
    inlines = [ChimePageInline]
    list_display = ["title", "order", "enable", "page_count", "rendered", "render_error"]
    list_editable = ["order", "enable"]
    list_filter = ["enable"]
    search_fields = ["title", "notes"]
    readonly_fields = ("page_count", "rendered", "render_error", "source_sha256")

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except chime_files.ChimeRenderError as e:
            self.message_user(request, "Saved, but the page images were not made: %s" % e,
                              messages.ERROR)


admin.site.register(ChimeTune, ChimeTuneAdmin)
