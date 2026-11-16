from django.urls import path, include
from django.contrib.auth.models import User
from rest_framework import routers, serializers, viewsets

from . import views
from . import models

from . import status_views
from . import controls
from . import chimes_views

# Serializers define the API representation
class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['url', 'username', 'email','is_staff']

class FunctionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Function
        fields = ['name', 'function', 'order','active']

# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class FunctionViewSet(viewsets.ModelViewSet):
    queryset = models.Function.objects.all()
    serializer_class = FunctionSerializer

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'functions', FunctionViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.


urlpatterns = [
    path('home/', views.home, name='home'),
    path('draw/', views.some_draw, name='draw'),
    path('menu/', views.menu, name ='menu'),
    path("chimes/player/state/", chimes_views.chime_player_state, name="chime_player_state"),
    path("chimes/player/play/", chimes_views.chime_player_play, name="chime_player_play"),
    path("chimes/player/stop/", chimes_views.chime_player_stop, name="chime_player_stop"),
    path("chimes/player/outputs/", chimes_views.chime_player_outputs, name="chime_player_outputs"),
    path("chimes/player/ports/", chimes_views.chime_player_ports, name="chime_player_ports"),
    path("chimes/", chimes_views.chimes, name="chimes"),
    path("chimes/<slug:slug>/", chimes_views.chime_page, name="chime_tune"),
    path("chimes/<slug:slug>/<int:page>/", chimes_views.chime_page, name="chime_page"),
    path("chimes/<slug:slug>/<int:page>/full/", chimes_views.chime_full, name="chime_full"),
    path("chimes/<slug:slug>/notemap.json", chimes_views.chime_notemap_json, name="chime_notemap"),
    path("chimes/<slug:slug>/<int:page>/image.png", chimes_views.chime_image, name="chime_image"),
    path("farm/status/", views.farm_status, name="farm_status"),
    path("farm/status/<int:index>/", views.farm_status, name="farm_status_index"),    path("swing/<int:n>/", views.swing_display, name="swing_display"),
    path('clock/analogue/', views.clock_analogue, name = 'analogue_clock'),
    path('clock/', views.clock, name = 'clock'),
    path('timedatestatus/', views.timedatestatus, name = 'timedatestatus'),
    path('timedatetest/', views.timedatetest, name = 'timedatetest'),
    path('d3_clock/', views.some_d3, name='D3_clock'),
    path('portrait/<int:number>/<str:to_name>/', views.portrait_view, name='portrait_view'),
    path('portrait/<int:number>/<str:to_name>/<str:from_name>/', views.portrait_view, name='tofrom_portrait_view'),
    path('pattern/<int:number>/', views.pattern_list, name = 'patterns_list'),
    path("bells/", views.bell_band, name="bell_band"),
    path("bells/<int:number>/", views.bell_band, name="bell_band_number"),
    path('random/', views.random_display, name='random_display'),
    path('random/<int:number>/', views.random_display, name='random_display_number'),
    path('random/<int:number>/<str:seed_name>/',views.random_display,name='random_display_seed',),
    path('<int:tower_id>/d3/',views.some_d3_base ,name= 'tower_D3'),
    path('<int:tower_id>/json/',views.tower_detail_json ,name= 'tower_json'),
    path('<int:tower_id>/pdf/', views.some_pdf_view, name='tower_pdf'),
    path('<int:number>/', views.display, name='number_index'),
    path('<int:number>/<str:to_name>/', views.display, name='to_index_view'),   
    path('<int:number>/<str:to_name>/<str:from_name>/', views.display, name='tofrom_index_view'),
    path('display/<int:number>/', views.display, name='display_number_index'),
    path('display/<int:number>/<str:to_name>/', views.display, name='display_to_index_view'),
    path('display/<int:number>/<str:to_name>/<str:from_name>/', views.display, name='display_tofrom_index_view'),
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('', views.home, name='root_home'),
    path("api/system-status/", status_views.system_status, name="system_status"),
    path("control/ping/", controls.control_ping, name="control_ping"),
    path("control/<str:name>/", controls.control_action, name="control_action"),
    path("api/farm/action/", views.farm_action, name="farm_action"),
    path("api/farm/device-status/",views.farm_device_status,name="farm_device_status"),
    path("farm/heads/", views.farm_heads, name="farm_heads"),
    path("farm/heads/<int:index>/", views.farm_heads, name="farm_heads_index"),
    path("farm/heads/serial/", views.farm_heads_serial, name="farm_heads_serial"),
    path("farm/heads/serial/cmd/", views.farm_heads_serial_cmd, name="farm_heads_serial_cmd"),
    path("farm/heads/pt-log.csv", views.farm_heads_pt_log, name="farm_heads_pt_log"),
    # the page's first name: still works, goes to /farm/heads/
    path("farm/align/", views.farm_align, name="farm_align"),
    path("farm/align/<int:index>/", views.farm_align, name="farm_align_index"),
    path("layout-test/<int:number>/<str:a>/<str:b>/<str:c>/", views.layout_test, name="layout_test"),
    path("layout-test/<int:number>/", views.layout_test, name="layout_test_default"),
]
