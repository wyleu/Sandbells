from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def sandtest_button(context):
    """{% sandtest_button %} -- the Sandtest button of the shared top line.
    Lit when the page being shown is the Sandtest page."""
    request = getattr(context, "request", None)
    url = reverse("sandtest:page")
    on = request is not None and request.path == url
    return format_html('<a class="navbtn sandtest{}" href="{}">Sandtest</a>',
                       " on" if on else "", url)
