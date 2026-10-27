from django import template

from bells import controls

register = template.Library()


@register.simple_tag
def power_machine(inst):
    """{% power_machine inst as machine %} -- this machine's name when inst is
    the farm entry for the machine running Sandbells, else "" (no buttons)."""
    if not inst or not controls.is_this_machine(inst):
        return ""
    return controls.machine_name()
