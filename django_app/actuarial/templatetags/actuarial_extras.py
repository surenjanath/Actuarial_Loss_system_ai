from django import template

register = template.Library()

_STATUS = {
    'active': 'Available',
    'busy': 'In Focus Mode',
    'in-meeting': 'In Meeting',
    'offline': 'Offline',
}


@register.filter
def status_label(status: str) -> str:
    return _STATUS.get(status, status)


@register.filter
def mul(value, arg) -> float:
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def min100(value) -> float:
    try:
        return min(100.0, float(value))
    except (ValueError, TypeError):
        return 0
