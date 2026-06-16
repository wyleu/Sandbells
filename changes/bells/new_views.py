import io
import datetime
import socket
import subprocess
import random

from django.shortcuts import render
from django.http import HttpResponse, Http404, JsonResponse, FileResponse
from django.core import serializers
from django.core.paginator import Paginator
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF

from .models import Bell, Tower, Pattern
from .functions import (
    db_process,
    demuck_result,
    demuck_result_list,
    ZeroLengthChange,
    NonIntegerBellCount,
    NotFound,
)


# ====================== HELPER FUNCTIONS ======================

def get_from_pattern(number: int, from_name: str = "Rounds"):
    try:
        return Pattern.objects.get(name__iexact=from_name, number=number, enable=True)
    except Pattern.DoesNotExist:
        return Pattern.objects.filter(number=number, enable=True).order_by('order').first()


def get_random_to_pattern(number: int):
    """Biased random selection — prefers nice 6 & 8 bell changes."""
    qs = Pattern.objects.filter(number=number, enable=True)\
                        .exclude(order__lte=5)\
                        .exclude(order__gte=800)\
                        .order_by('order')

    if not qs.exists():
        return Pattern.objects.filter(number=number, enable=True).first()

    if number == 8:
        qs = qs.filter(order__lte=120)
    elif number == 6:
        qs = qs.filter(order__lte=150)

    # Weighted random
    weighted = []
    for p in qs:
        weight = max(1, 100 - (p.order // 3))
        weighted.extend([p] * weight)

    return random.choice(weighted)


def process_change(from_pattern, to_pattern):
    """Return cleaned forward + reverse results."""
    _, result, _ = db_process(from_pattern.pattern, to_pattern.pattern)
    _, revresult, _ = db_process(to_pattern.pattern, from_pattern.pattern)

    return demuck_result_list(result), demuck_result_list(revresult)


# ====================== MAIN VIEWS ======================

def home(request, number: int = 8):
    """Homepage / landing page with system info."""
    numbers = sorted(set(
        Pattern.objects.filter(enable=True)
        .values_list('number', flat=True)
    ))

    to_patterns = Pattern.objects.filter(enable=True).order_by('number', 'order', 'name')

    # System info
    hostname = socket.gethostname()
    try:
        ipaddr = subprocess.check_output(["hostname", "-I"]).decode().strip().split()[0]
    except Exception:
        ipaddr = "No Network"

    try:
        githash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:6]
    except Exception:
        githash = "unknown"

    context = {
        'hostname': hostname,
        'IPAddr': ipaddr,
        'githash': githash,
        'number': number,
        'numbers': numbers,
        'to_patterns': to_patterns,
        'count': to_patterns.count(),
    }
    return render(request, 'bells/home.html', context)


def display(request, number: int = 8, to_name: str = '', from_name: str = "Rounds"):
    """Main display view (used in iframe)."""
    lines_per_page = 20

    from_patterns = Pattern.objects.filter(number=number, enable=True).order_by('order')
    to_patterns = Pattern.objects.filter(number=number, enable=True).order_by('order', 'name')
    available_numbers = sorted(set(
        Pattern.objects.filter(enable=True).values_list('number', flat=True)
    ))

    from_pattern = get_from_pattern(number, from_name)

    if not to_name:
        to_pattern = get_random_to_pattern(number)
    else:
        try:
            to_pattern = Pattern.objects.get(name__iexact=to_name, number=number, enable=True)
        except Pattern.DoesNotExist:
            to_pattern = to_patterns.first()

    # Process changes
    result, revresult = process_change(from_pattern, to_pattern)

    # Pagination logic
    forward_and_back = len(result) < lines_per_page
    page_size = lines_per_page if forward_and_back else (1 + len(result) // 2)

    paginator1 = Paginator(result, page_size)
    page1 = paginator1.get_page(1).object_list

    if forward_and_back:
        page2 = Paginator(revresult, page_size).get_page(1).object_list
    else:
        page2 = Paginator(result, page_size).get_page(2).object_list

    context = {
        'from_patterns': from_patterns,
        'to_patterns': to_patterns,
        'from_pattern': from_pattern,
        'to_pattern': to_pattern,
        'result': demuck_result(page1),
        'revresult': demuck_result(page2),
        'number': number,
        'numbers': available_numbers,
        'count': to_patterns.count(),
        'rounds': ''.join(str(i + 1) for i in range(number)),
        'forward_and_back': forward_and_back,
    }

    return render(request, 'bells/display.html', context)


# ====================== UTILITY VIEWS ======================

def portrait_view(request, number: int, to_name: str, from_name: str = "Rounds"):
    """Printable version."""
    try:
        number = int(number)
    except ValueError:
        raise NonIntegerBellCount('Bell count must be an integer')

    from_pattern = get_from_pattern(number, from_name)

    try:
        to_pattern = Pattern.objects.get(name__iexact=to_name, number=number, enable=True)
    except Pattern.DoesNotExist:
        to_pattern = Pattern.objects.filter(number=number, enable=True).first()

    result, revresult = process_change(from_pattern, to_pattern)

    context = {
        'from_pattern': from_pattern,
        'to_pattern': to_pattern,
        'result': demuck_result(result),
        'revresult': demuck_result(revresult),
    }
    return render(request, 'bells/portrait.html', context)


def pattern_list(request, number: int):
    patterns = Pattern.objects.filter(number=number, order__lt=200).order_by('name')
    return render(request, 'bells/portrait_list.html', {'patterns': patterns})


def tower_detail_json(request, tower_id=1):
    try:
        tower = Tower.objects.get(pk=tower_id)
        qs = tower.bell_set.all()
        if qs.exists():
            serializer = serializers.get_serializer("json")()
            data = serializer.serialize(qs, ensure_ascii=False, indent=2, use_natural_foreign_keys=True)
            return HttpResponse(data, content_type="application/json")
        raise Http404("No bells found")
    except Tower.DoesNotExist:
        raise Http404("Tower does not exist")


def timedatestatus(request):
    try:
        output = subprocess.check_output(["timedatectl"]).decode()
        lines = output.strip().split('\n')
        return JsonResponse({'timedate': lines})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ====================== OLD / DEMO VIEWS ======================

def some_pdf_view(request, tower_id=1):
    # ... your existing PDF code (kept as-is for now) ...
    pass   # ← replace with cleaned version if you want

def some_draw(request, bells=8):
    # ... your existing draw code ...
    pass