"""URL routes for the Snapper UI.

The host includes this module at its chosen prefix, e.g.::

    path('snapper/', include('snapper_ai.urls'))

Route names live in the ``snapper_ai`` namespace.
"""

from django.urls import path

from . import views

app_name = 'snapper_ai'

urlpatterns = [
    path('', views.snapper_root, name='snapper_root'),
    path('<str:scope>/report/', views.snapper_report,
         name='snapper_report'),
    path('<str:scope>/prefs/', views.snapper_prefs_save,
         name='snapper_prefs'),
    path('<str:scope>/cut/', views.snapper_cut, name='snapper_cut'),
    path('<str:scope>/activity/', views.snapper_activity,
         name='snapper_activity'),
    path('<str:scope>/report/<uuid:snap_id>/', views.snapper_report,
         name='snapper_report_snap'),
    path('<str:scope>/system/', views.snapper_system,
         name='snapper_system'),
]
