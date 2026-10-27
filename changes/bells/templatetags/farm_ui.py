"""{% machine_photo %} -- the one place a machine's picture is drawn.

    {% load farm_ui %}
    {% machine_photo inst %}                      header size, 112 px
    {% machine_photo "sandswing" size=40 %}       small spot (uses the 160 px thumbnail)
    {% machine_photo inst size=96 placeholder=True %}   neutral square if there is no photo

The first argument is a farm registry entry (a dict: id, name, host are tried
in that order) or a plain key string.  With no photo the tag draws nothing
(or, with placeholder=True, a neutral rounded square with the first letter),
so a page never shows a broken-image icon.  The cache-busting ?v=<git hash>
comes from the page's git_hash context, like the css and js urls.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from bells import farm_photos

register = template.Library()

DEFAULT_SIZE = 112


def _keys(machine):
    if isinstance(machine, dict):
        return [machine.get("id"), machine.get("name"), machine.get("host")]
    return [machine]


def _label(machine):
    if isinstance(machine, dict):
        return str(machine.get("name") or machine.get("id") or "")
    return str(machine or "")


@register.simple_tag(takes_context=True)
def machine_photo(context, machine, size=DEFAULT_SIZE, placeholder=False):
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = DEFAULT_SIZE
    size = max(16, min(size, 300))
    name = _label(machine)
    paths = farm_photos.photo_for(*_keys(machine))
    if paths is None:
        if not placeholder:
            return ""
        return format_html(
            '<span class="mphoto mphoto-none" style="--s:{0}px" aria-hidden="true">{1}</span>',
            size, (name[:1] or "?").upper())
    path = paths[1] if size <= farm_photos.THUMB_MAX_PX else paths[0]
    ver = context.get("git_hash") or "dev"
    # onerror: a file that has not been collected yet leaves the neutral
    # square, never the browser's broken-image icon.
    return format_html(
        '<span class="mphoto" style="--s:{size}px">'
        '<img src="{src}?v={ver}" width="{size}" height="{size}" alt="{alt}" '
        'loading="lazy" decoding="async" onerror="this.hidden=true"></span>',
        size=size, src=static(path), ver=ver, alt=name)
