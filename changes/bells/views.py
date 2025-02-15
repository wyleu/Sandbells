from django.shortcuts import render

import io
import datetime
import socket
import subprocess
import json

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.graphics.shapes import *
from django.core import serializers
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.http import Http404
from django.http import JsonResponse
from django.http import FileResponse
from django.shortcuts import render
from django.template import loader


from bells.models import Bell, Tower, Pattern
from bells.functions import (
    db_process,
    ZeroLengthChange, 
    NonIntegerBellCount,
    NotFound)

def home(request, number = 8 ):
    # Render the iframe container
    context = {}


        # Render menu 
    numbers = set(
        Pattern.objects.filter(
        enable=True
        ).order_by('number')
        .values_list('number', flat=True))

    numbers= sorted(numbers)

    to_patterns = Pattern.objects.filter(
        enable=True
        ).order_by('number', 'order','name') 
    
    hostname = socket.gethostname().replace('"','')
    # hostname -I  for ip address
##
    p = subprocess.Popen(["hostname", "-I"], stdout=subprocess.PIPE)
    hostname_out, err = p.communicate()
    try:
        ipaddr = [x.decode("utf-8").replace("'",'') for x in hostname_out.split()][0]
    except IndexError:
        ipaddr = "No Net"

    p = subprocess.Popen(["git", "rev-parse", "HEAD"], stdout=subprocess.PIPE)
    gitlog_out, err = p.communicate()
    githash = [x.decode("utf-8").replace("'",'') for x in gitlog_out.split()][0][0:6]

    context = {
        'hostname': hostname,
        'IPAddr': ipaddr,
        'githash': githash,
        'number' : number,
        'numbers' : numbers,
        'to_patterns': to_patterns,
        'count': len(to_patterns),
        }
    
    return render(request, 'bells/home.html', context)

def menu(request, number = 8):
    # Render menu 
    numbers = set(
        Pattern.objects.filter(
            enable=True
        ).order_by('number')
        .values_list('number', flat=True))

    to_patterns = Pattern.objects.filter(
        enable=True
        ).order_by('number','order','name') 
    
                   

    context = {
        'number' : number,
        'numbers' : numbers,
        'count': len(to_patterns),
        'to_patterns': to_patterns
        }
    
    response=  render(request, 'bells/menu.html', context)
    # The following allows content in iframe windows.
    # response ['Content-Security-Policy'] = "frame-ancestors 'self' http://localhost:8000/"
    return response

def display(request,  number = 8, to_name='', from_name="Rounds"):    # iframe contents

    lines_per_page = 20

    from_patterns = Pattern.objects.filter(
        number=number,
        enable = True
    ).order_by('order')  
    to_patterns = Pattern.objects.filter(
        number=number,
        enable=True
    ).order_by('order','name') 

    numbers = set(Pattern.objects.filter(enable=True).order_by('number').values_list('number', flat=True))

    try:
        from_pattern = Pattern.objects.get(
            name__iexact = from_name,
            number = number,
            enable=True
        )
    except  Pattern.DoesNotExist:
        raise NotFound("No From Pattern Found")
    
    try:
        to_pattern = Pattern.objects.get(
            name__iexact = to_name,
            number = number,
            enable=True

        )
    except  Pattern.DoesNotExist:
        context = {
               'from_patterns':from_patterns,
               'to_patterns':to_patterns,
               'from_pattern':from_pattern,
               'number': int(number),
               'numbers': sorted(numbers)
        }
    
        response = render(request, 'bells/display.html', context)
        # response ['Content-Security-Policy'] = "frame-ancestors 'self' http://localhost:8000/"
        return response
        
    code, result, swappair = db_process(from_pattern.pattern, to_pattern.pattern)
    revcode, revresult, swappair = db_process(to_pattern.pattern, from_pattern.pattern)

    to_pattern.populate_count(len(result[0])-1)

    result = demuck_result_list(result)
    revresult = demuck_result_list(revresult) 
    

    if len(result) < lines_per_page:
        forward_and_back = True
    else:
        forward_and_back = False
        lines_per_page = int(1 + len(result) / 2 )

    paginator1 = Paginator(result, lines_per_page)
    page1 = paginator1.get_page(1).object_list

    if forward_and_back:
        # Two Forward & Back
        paginator2 = Paginator(revresult, lines_per_page)
        page2 = paginator2.get_page(1).object_list 
    else:
        paginator2 = Paginator(result, lines_per_page)
        page2 = paginator2.get_page(2).object_list
    
    forwresult = demuck_result(page1)
    revresult = demuck_result(page2)

    rounds = ''.join([ str(no+1) for no in range(number)])

    context = {'from_patterns':from_patterns,
               'to_patterns':to_patterns,
               'from_pattern':from_pattern,
               'to_pattern':to_pattern,
               "result": forwresult,
               "revresult": revresult,
               "result_block" : [forwresult, revresult],
               'number': int(number),
               'numbers': sorted(numbers),
               'count': len(to_patterns),
               'page1': page1,
               'page2': page2,
               'rounds': rounds,
               'forward_and_back': forward_and_back,
               }
    
    response = render(request, 'bells/display.html', context)
    # response ['Content-Security-Policy'] = "frame-ancestors 'self' http://localhost:8000/"
    return response

def tower_detail_json(request, tower_id=1):
    try:
        tower = Tower.objects.get(pk=tower_id)
        qs = tower.bell_set.all()
        # qs = Bell.objects.select_related("tower").filter(tower=tower_id)
        if qs.exists():
            jSONSerializer = serializers.get_serializer("json")
            json_serializer = jSONSerializer()
            response =  json_serializer.serialize(
                qs,
                ensure_ascii=False,
                indent=2,
                # use_natural_foreign_keys=True,
                use_natural_foreign_keys=True
                )
            return HttpResponse(response, content_type="application/json")
        else:
            raise Http404("Tower does not exist")
    except Tower.DoesNotExist:
        raise Http404("An Error in tower_detail_json")

def some_d3(request, bells=1):
    
    # Generate a D3 representation of a change of bells
    now = datetime.datetime.now()
    html = "<html><body>It is now %s.</body></html>" % now
    return HttpResponse(html)

def some_d3_base(request, tower_id): 
    # Generate a D3 representation of a Tower

    try:
        t = Tower.objects.get(pk=tower_id)
    except Tower.DoesNotExist:
        raise Http404("Bell does not exist")
    context = {'tower':t,}
    return render(request, 'bells/bellsd3circle.html', context)

def clock_analogue(request):
    context = {}
    return render(request, 'bells/clock_analogue.html', context)

def clock(request):
    context = {}
    return render(request, 'bells/clock.html', context)

def portrait_view(request, number, to_name, from_name="Rounds"):
    # A printable list of a change
    #TODO make the implicit "Rounds" explicit 
    # to_pattern = Pattern.objects.get(order=0) Perhaps?
    
    try:
        number=int(number)
    except ValueError:
        raise NonIntegerBellCount('Bells number not an Integer')

    try:
        from_pattern = Pattern.objects.get(
            name__iexact = from_name,
            number = number
        )

    except  Pattern.DoesNotExist:
        from_patterns = Pattern.objects.filter(
            name__icontains = from_name,
            number = number
        ).order_by('order','name',)
        if from_patterns:
            from_pattern = from_patterns[0]
        else:
            raise NotFound("No From Pattern Found")
    
    try:
        to_pattern = Pattern.objects.get(
            name__iexact = to_name,
            number = number
        )
    except  Pattern.DoesNotExist:
        to_patterns = Pattern.objects.filter(
            name__icontains =to_name,
            number = number
        ).order_by('order','name',)
        if to_patterns:
            to_pattern = to_patterns[0]
        else:
            raise NotFound("No To Pattern Found")
 

    code, result, swappair = db_process(from_pattern.pattern, to_pattern.pattern)
    revcode, revresult, swappair = db_process(to_pattern.pattern, from_pattern.pattern)

    forwresult = demuck_result(result)
    revresult = demuck_result(revresult)

    context = {'to_pattern': to_pattern,
               'from_pattern': from_pattern,
               "result": forwresult,
               "revresult": revresult
               }
    return render(request, 'bells/portrait.html', context)

def pattern_list(request, number):
    # A list of known patterns filtered by numbers
    patterns = Pattern.objects.filter(number=number, order__lt=200).order_by('name')
    context = {
        'patterns' : patterns
    }
    return render(request, 'bells/portrait_list.html', context)

def some_pdf_view(request, tower_id=1):
    # Generate a PDF representation of a Tower 
    # Create a file-like buffer to receive PDF data.

    bells = Tower.objects.get(pk=tower_id).bell_set.all().count()
    buffer = io.BytesIO()

    # Create the PDF object, using the buffer as its "file."
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = letter  # keep for later

    # Draw things on the PDF. Here's where the PDF generation happens.
    # See the ReportLab documentation for the full list of functionality.
    p.drawString(100, 100, "Hello world.")
    p.drawCentredString(200, 200, "A Bell")
    p.line(0, 0, x2=width, y2=height)
    p.line(width, 0, x2=0, y2=height)
    for i in range(bells):
        circle_centre_x = (width/bells) * i
        circle_centre_y = (height/bells) * i
        p.circle(circle_centre_x, circle_centre_y, 10*i, stroke=1, fill=0)
    p.circle(width, height, 10*i, stroke=1, fill=0)

 
    # vertical
    for j in range(1, int(width), 100):
        p.line(j, 1, x2=j, y2=height*2)
    # horizontal
    for k in range(1, int(height) * 2 , 100):
        p.line(1, k, x2=width, y2=k)

    # # Diagonal
    # for k in range(-1000, 1000, 100):
    #     p.line(k, -100, x2=k+1000, y2=900)
    # for k in range(1, 2000, 100):
    #     p.line(-100, k, x2=900, y2=k-1000)



    # Close the PDF object cleanly, and we're done.
    p.showPage()
    p.save()

    # FileResponse sets the Content-Disposition header so that browsers
    # present the option to save the file.
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='hello.pdf')

def some_draw(request, bells=8):
    # Create a file-like buffer to receive PDF data.
    buffer = io.BytesIO()
        # Create the PDF object, using the buffer as its "file."
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = letter  # keep for later

    d = Drawing(400, 200)
    d.add(Rect(50, 50, 300, 100, fillColor=colors.yellow))
    d.add(String(150,100, 'Hello World', fontSize=18, fillColor=colors.red))
    d.add(String(180,86, 'Special characters'
        '\xc2\xa2\xc2\xa9\xc2\xae\xc2\xa3\xce\xb1\xce\xb2',
                fillColor=colors.red))

    from reportlab.graphics import renderPDF
    renderPDF.drawToFile(d, buffer, 'My First Drawing')
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='draw.pdf')

# General functions

def demuck_result(result):
    res_string = []
    for index, pair in enumerate(result):
        if result[index][1]:
            swaptwopair = '%s%s' % (result[index][0],result[index][1][5])
        else:
            swaptwopair = "££"
        res_dict = {'pattern':pair[0],
                    'first': pair[1],
                    'second':pair[2],
                    'third': pair[3],
                    'swappair': pair[4],
                    'index': pair[5]
                    }
        res_string.append(res_dict)
    return res_string

def demuck_result_list(result):
    res_string = []
    for index, pair in enumerate(result[0]):
        if result[1][index][1]:
            swaptwopair = '%s%s' % (result[1][index][1][0],result[1][index][1][5])
            index_count = result[1][index][4]
        else:
            swaptwopair = "££"
            index_count =  ''
        res_list = [pair,
                    result[1][index][0],
                    result[1][index][1],
                    result[1][index][2],
                    swaptwopair,
                    index_count,
                    ]
        res_string.append(res_list)
    return res_string

def timedatestatus(request):

    response_data = {}
    response_data['result'] = 'error'
    response_data['message'] = 'Some error message'
    p = subprocess.Popen(["timedatectl",], stdout=subprocess.PIPE)
    timedate_out, err = p.communicate()
    td = [x.decode("utf-8").replace("'",'') for x in timedate_out.split()]
    print(td)
    timedate = [' '.join([td[0],td[1]]), ' '.join([td[2],td[3],td[4],td[5],])]                   # Local Time
    timedate = [' '.join([td[6],td[7]]), ' '.join([td[8],td[9],td[10],td[11],])] + timedate      # Universal Time
    timedate = [' '.join([td[12],td[13]]), ' '.join([td[14],td[15],td[16],])] + timedate         # RTC Time
    timedate = [' '.join([td[17],td[18]]), ' '.join([td[19],td[20],td[21],])] + timedate         # TimeZone
    timedate = [' '.join([td[22],td[23],td[24]]), ' '.join([td[25],])] + timedate                # Syncronised
    timedate = [' '.join([td[26],td[27]]), ' '.join([td[28],])] + timedate                       # Service
    timedate = [' '.join([td[29],td[30],td[31],td[32],]), ' '.join([td[33],])] + timedate
    return JsonResponse({'timedate':timedate})

def timedatetest(request):
    return render(request, 'bells/timedatetest.html')

