from django.urls import path

from . import crew_views, views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('members/', views.members, name='members'),
    path('crew/runs/', views.crew_runs, name='crew_runs'),
    path('integrations/', views.ai_integrations, name='ai_integrations'),
    path('database/', views.database, name='database'),
    path('statistics/', views.statistics, name='statistics'),
    path('settings/', views.settings_view, name='settings'),
    path('export/actuarial.csv', views.export_actuarial_csv, name='export_actuarial_csv'),
    path('export/members.csv', views.export_members_csv, name='export_members_csv'),
    path('api/actuarial.json', views.actuarial_json, name='actuarial_json'),
    path('api/members/customize/', views.save_member_personalization, name='save_member_personalization'),
    path(
        'api/members/crew-instructions/',
        views.save_crew_instructions,
        name='save_crew_instructions',
    ),
    path(
        'api/members/personalization/reset/',
        views.reset_team_personalization,
        name='reset_team_personalization',
    ),
    path('api/crew/pipeline/', views.crew_pipeline_api, name='crew_pipeline_api'),
    path('api/settings/company/', views.company_profile_api, name='company_profile_api'),
    path('api/settings/ollama/', views.save_ollama_settings, name='save_ollama_settings'),
    path(
        'api/settings/ollama/models/',
        views.ollama_models_list,
        name='ollama_models_list',
    ),
    path('api/crew/health/', crew_views.crew_health, name='crew_health'),
    path('api/crew/stream/', crew_views.crew_stream, name='crew_stream'),
    path('api/crew/runs/latest/', crew_views.crew_run_latest, name='crew_run_latest'),
    path('api/crew/runs/list/', crew_views.crew_run_list, name='crew_run_list'),
    path(
        'api/crew/runs/<uuid:run_id>/',
        crew_views.crew_run_detail,
        name='crew_run_detail',
    ),
    path(
        'api/crew/runs/<uuid:run_id>/pdf/',
        crew_views.crew_run_pdf,
        name='crew_run_pdf',
    ),
    path(
        'api/crew/runs/<uuid:run_id>/approve/',
        crew_views.crew_run_approve,
        name='crew_run_approve',
    ),
    path(
        'api/crew/runs/<uuid:run_id>/delete/',
        crew_views.crew_run_delete,
        name='crew_run_delete',
    ),
    path(
        'api/crew/runs/<uuid:run_id>/board/',
        crew_views.crew_run_board,
        name='crew_run_board',
    ),
    path(
        'api/crew/runs/<uuid:run_id>/events/',
        crew_views.crew_run_events,
        name='crew_run_events',
    ),
    path('crew/board/', crew_views.crew_board_page, name='crew_board'),
    path('actions/regenerate-data/', views.regenerate_actuarial_data, name='regenerate_actuarial_data'),
]
