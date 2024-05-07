from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home, name='home'),
    path('show/',views.index, name="show"),
    path('draw/', views.some_draw, name='draw'),
    path('menu/', views.menu, name ='menu'),
    path('clock/analogue/', views.clock_analogue, name = 'analogue_clock'),
    path('clock/', views.clock, name = 'clock'),
    path('d3_clock/', views.some_d3, name='D3_clock'),
    path('portrait/<int:number>/<str:to_name>/', views.portrait_view, name='portrait_view'),
    path('portrait/<int:number>/<str:to_name>/<str:from_name>/', views.portrait_view, name='tofrom_portrait_view'),
    path('pattern/<int:number>/', views.pattern_list, name = 'patterns_list'),
    path('<int:tower_id>/d3/',views.some_d3_base ,name= 'tower_D3'),
    path('<int:tower_id>/json/',views.tower_detail_json ,name= 'tower_json'),
    path('<int:tower_id>/pdf/', views.some_pdf_view, name='tower_pdf'),
    path('<int:number>/', views.display, name='number_index'),
    path('<int:number>/<str:to_name>/', views.display, name='to_index_view'),   
    path('<int:number>/<str:to_name>/<str:from_name>/', views.display, name='tofrom_index_view'),
    path('display/<int:number>/', views.display, name='display_number_index'),
    path('display/<int:number>/<str:to_name>/', views.display, name='display_to_index_view'),
    path('display/<int:number>/<str:to_name>/<str:from_name>/', views.display, name='display_tofrom_index_view'),
    path('', views.home, name='root_home'),


]