import csv
import json

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import crew_config, member_personalization, ollama_session, services, workspace_state
from .company_profile import get_company_profile, set_company_profile
from .workspace_user_profile import (
    get_workspace_user_profile,
    resolve_workspace_user_display,
    set_workspace_user_profile,
)
from .persona_defaults import DEFAULT_GLOBAL_CREW_BRIEF


def _get_rows(request):
    rng = services.rng_for_request(request)
    return services.generate_actuarial_data(rng)


def _safe_next_path(raw: str) -> str:
    path = (raw or '').strip()
    if len(path) > 256 or not path.startswith('/'):
        return '/'
    if path.startswith('//') or '://' in path:
        return '/'
    return path


@login_required
def dashboard(request):
    actuarial_data = _get_rows(request)
    target_loss_ratio = 0.68
    weight_incurred = 0.4
    weight_trend = 0.3
    weight_reserve = 0.3
    vulnerability_probabilities = services.calculate_vulnerability_probability(
        actuarial_data,
        target_loss_ratio,
        weight_incurred,
        weight_trend,
        weight_reserve,
    )
    max_probability = max(vulnerability_probabilities + [1.0])
    metrics = services.dashboard_metrics(
        actuarial_data, vulnerability_probabilities, target_loss_ratio
    )
    particle_data_js = services.particle_rows_for_js(actuarial_data)
    dashboard_data_js = services.actuarial_rows_for_js_dashboard(actuarial_data)

    total_functions_display = services.format_number(metrics['years_analyzed'] * 1000)
    issues_display = services.format_number(int(metrics['avg_vulnerability'] * 10))
    health_pct = f"{(100 - metrics['avg_vulnerability']):.1f}%"

    best_year = min(actuarial_data, key=lambda y: y['loss_ratio'])
    worst_year = max(actuarial_data, key=lambda y: y['loss_ratio'])

    best_year_lr = services.format_percentage(best_year['loss_ratio'])
    worst_year_lr = services.format_percentage(worst_year['loss_ratio'])
    avg_lr_str = services.format_percentage(metrics['avg_loss_ratio'])
    target_lr_str = services.format_percentage(target_loss_ratio)
    year_range_label = (
        f"{actuarial_data[0]['accident_year']}–{actuarial_data[-1]['accident_year']}"
        if actuarial_data
        else ''
    )

    return render(
        request,
        'actuarial/dashboard.html',
        {
            'actuarial_data': actuarial_data,
            'max_probability': max_probability,
            'metrics': metrics,
            'particle_data_js': particle_data_js,
            'dashboard_data_js': dashboard_data_js,
            'target_loss_ratio': target_loss_ratio,
            'weight_incurred': weight_incurred,
            'weight_trend': weight_trend,
            'weight_reserve': weight_reserve,
            'total_functions_display': total_functions_display,
            'issues_display': issues_display,
            'health_pct': health_pct,
            'best_year': best_year,
            'worst_year': worst_year,
            'best_year_lr': best_year_lr,
            'worst_year_lr': worst_year_lr,
            'avg_lr_str': avg_lr_str,
            'target_lr_str': target_lr_str,
            'year_range_label': year_range_label,
        },
    )


def _crew_pipeline_bundle(request):
    pipeline = crew_config.get_pipeline(request)
    crew_display = []
    for row in pipeline:
        r = dict(row)
        r['display_label'] = crew_config.display_label(row)
        r['step_subtitle'] = crew_config.step_kind_subtitle(str(row.get('step_kind') or ''))
        sk = str(row.get('step_kind') or 'generic')
        wlid, wltitle = crew_config.workflow_lane_for_step_kind(sk)
        r['workflow_lane'] = wlid
        r['workflow_lane_title'] = wltitle
        crew_display.append(r)
    departments = sorted(
        {a.get('department') or '' for a in pipeline if (a.get('department') or '').strip()}
    )
    crew_display_lanes = crew_config.crew_display_by_lanes(crew_display)
    return pipeline, crew_display, departments, crew_display_lanes


@login_required
def members(request):
    pipeline, crew_display, departments, _crew_display_lanes = _crew_pipeline_bundle(request)
    return render(
        request,
        'actuarial/members.html',
        {
            'crew_pipeline': pipeline,
            'crew_display': crew_display,
            'crew_step_kinds': crew_config.STEP_KIND_CHOICES,
            'crew_pipeline_min': crew_config.MIN_PIPELINE_LEN,
            'crew_pipeline_max': crew_config.MAX_PIPELINE_LEN,
            'departments': departments,
        },
    )


@login_required
def crew_runs(request):
    _, crew_display, _, crew_display_lanes = _crew_pipeline_bundle(request)
    return render(
        request,
        'actuarial/crew_runs.html',
        {
            'crew_display': crew_display,
            'crew_display_lanes': crew_display_lanes,
            'crew_step_tracker': crew_config.step_tracker_map_all(),
            'crew_pipeline_min': crew_config.MIN_PIPELINE_LEN,
            'crew_pipeline_max': crew_config.MAX_PIPELINE_LEN,
            'crew_analysis_enabled': django_settings.CREW_ANALYSIS_ENABLED,
            'crew_global_instructions': member_personalization.get_global_instructions(
                request
            ),
            'default_crew_brief': DEFAULT_GLOBAL_CREW_BRIEF,
            'team_members': member_personalization.merged_team_members(request),
        },
    )


@login_required
def ai_integrations(request):
    return render(
        request,
        'actuarial/ai_integrations.html',
        {
            'ollama_env': ollama_session.env_defaults(),
            'crew_analysis_enabled': django_settings.CREW_ANALYSIS_ENABLED,
        },
    )


SORT_FIELDS = {
    'accident_year': 'accident_year',
    'reported_claims': 'reported_claims',
    'paid_losses': 'paid_losses',
    'incurred_losses': 'incurred_losses',
    'earned_premium': 'earned_premium',
    'loss_ratio': 'loss_ratio',
    'trend': 'trend',
    'risk_score': 'risk_score',
}


@login_required
def database(request):
    raw = list(_get_rows(request))
    q = (request.GET.get('q') or '').strip().lower()
    if q:
        data = [
            item
            for item in raw
            if (
                q in str(item['accident_year'])
                or q in str(item['reported_claims'])
                or q in item['trend'].lower()
            )
        ]
    else:
        data = list(raw)

    sort_field = request.GET.get('sort', 'accident_year')
    if sort_field not in SORT_FIELDS:
        sort_field = 'accident_year'
    sort_dir = request.GET.get('dir', 'desc')
    reverse = sort_dir != 'asc'
    key = SORT_FIELDS[sort_field]

    def sort_key(row):
        return row[key]

    data.sort(key=sort_key, reverse=reverse)

    total_premium = sum(y['earned_premium'] for y in raw)
    total_incurred = sum(y['incurred_losses'] for y in raw)
    avg_lr = sum(y['loss_ratio'] for y in raw) / len(raw)

    return render(
        request,
        'actuarial/database.html',
        {
            'data': data,
            'sort_field': sort_field,
            'sort_dir': sort_dir,
            'search_q': request.GET.get('q') or '',
            'total_records': len(raw),
            'total_premium': total_premium,
            'total_incurred': total_incurred,
            'avg_loss_ratio_pct': avg_lr * 100,
        },
    )


@login_required
def statistics(request):
    actuarial_data = _get_rows(request)
    stats = services.statistics_summary(actuarial_data)
    chart_data_js = services.chart_data_for_js(actuarial_data)
    return render(
        request,
        'actuarial/statistics.html',
        {
            'data': actuarial_data,
            'stats': stats,
            'chart_data_js': chart_data_js,
        },
    )


@login_required
def settings_view(request):
    rt = ollama_session.get_runtime_config(request)
    env = ollama_session.env_defaults()
    return render(
        request,
        'actuarial/settings.html',
        {
            'ollama_runtime': rt,
            'ollama_env': env,
        },
    )


@login_required
@require_GET
def export_actuarial_csv(request):
    rows = _get_rows(request)
    response = HttpResponse(
        content_type='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="actuarial_accident_years.csv"',
        },
    )
    writer = csv.writer(response)
    writer.writerow(list(services.ACTUARIAL_EXPORT_FIELDS))
    for row in rows:
        writer.writerow([row[k] for k in services.ACTUARIAL_EXPORT_FIELDS])
    return response


@login_required
@require_GET
def export_members_csv(request):
    pipeline = crew_config.get_pipeline(request)
    fields = (
        'id',
        'step_kind',
        'role',
        'goal',
        'backstory',
        'ollama_model',
        'label',
        'department',
        'avatar',
    )
    response = HttpResponse(
        content_type='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="crew_agents.csv"',
        },
    )
    writer = csv.writer(response)
    writer.writerow(fields)
    for row in pipeline:
        writer.writerow([row.get(k, '') for k in fields])
    return response


@login_required
@require_GET
def actuarial_json(request):
    rows = _get_rows(request)
    seed = services.ensure_actuarial_seed(request)
    payload = {
        'meta': {
            'count': len(rows),
            'dataset_seed': seed,
            'session_seed': seed,
        },
        'years': services.actuarial_rows_for_api(rows),
    }
    return JsonResponse(payload)


@login_required
@require_POST
def save_member_personalization(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    if body.get('action') == 'clear_member':
        mid = str(body.get('id', '')).strip()
        if not mid:
            return JsonResponse({'ok': False, 'error': 'Missing id'}, status=400)
        member_personalization.clear_member_override(request, mid)
        return JsonResponse({'ok': True})
    mid = str(body.get('id', '')).strip()
    if not mid:
        return JsonResponse({'ok': False, 'error': 'Missing id'}, status=400)
    patch = {}
    for k in (
        'name',
        'role',
        'department',
        'avatar',
        'specialization',
        'notes',
        'ai_instructions',
    ):
        if k in body:
            patch[k] = body[k]
    ok, err = member_personalization.patch_member_override(request, mid, patch)
    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=400)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def save_crew_instructions(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    txt = body.get('global_instructions')
    if txt is not None:
        member_personalization.set_global_instructions(request, str(txt))
    return JsonResponse({'ok': True})


@login_required
@require_POST
def crew_pipeline_api(request):
    """Configure Crew agent pipeline (database): save list, add/remove agent, reset defaults."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    action = (body.get('action') or '').strip()

    if action == 'set_pipeline':
        ok, err = crew_config.set_pipeline(request, body.get('pipeline') or [])
        return JsonResponse(
            {
                'ok': ok,
                'error': err,
                'pipeline': crew_config.get_pipeline(request),
            }
        )

    if action == 'add_agent':
        pl = list(crew_config.get_pipeline(request))
        if len(pl) >= crew_config.MAX_PIPELINE_LEN:
            return JsonResponse(
                {'ok': False, 'error': f'Maximum {crew_config.MAX_PIPELINE_LEN} agents.'},
                status=400,
            )
        pl.append(crew_config.default_generic_row())
        ok, err = crew_config.set_pipeline(request, pl)
        return JsonResponse(
            {
                'ok': ok,
                'error': err,
                'pipeline': crew_config.get_pipeline(request),
            }
        )

    if action == 'delete_agent':
        pid = str(body.get('id') or '').strip()
        if not pid:
            return JsonResponse({'ok': False, 'error': 'Missing id'}, status=400)
        pl = [r for r in crew_config.get_pipeline(request) if r.get('id') != pid]
        ok, err = crew_config.set_pipeline(request, pl)
        return JsonResponse(
            {
                'ok': ok,
                'error': err,
                'pipeline': crew_config.get_pipeline(request),
            }
        )

    if action == 'reset_defaults':
        workspace_state.migrate_legacy_session(request)
        crew_config.reset_pipeline_to_defaults()
        return JsonResponse({'ok': True, 'pipeline': crew_config.get_pipeline(request)})

    return JsonResponse({'ok': False, 'error': 'Unknown action'}, status=400)


@login_required
@require_POST
def reset_team_personalization(request):
    member_personalization.clear_all_overrides(request)
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['GET', 'POST'])
def workspace_user_api(request):
    if request.method == 'GET':
        return JsonResponse(
            {
                'ok': True,
                'profile': resolve_workspace_user_display(),
                'stored': get_workspace_user_profile(),
            }
        )
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    ok, err = set_workspace_user_profile(body if isinstance(body, dict) else {})
    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=400)
    return JsonResponse(
        {
            'ok': True,
            'profile': resolve_workspace_user_display(),
            'stored': get_workspace_user_profile(),
        }
    )


@login_required
@require_http_methods(['GET', 'POST'])
def company_profile_api(request):
    if request.method == 'GET':
        return JsonResponse({'ok': True, 'profile': get_company_profile(request)})
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    ok, err = set_company_profile(request, body if isinstance(body, dict) else {})
    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=400)
    return JsonResponse({'ok': True, 'profile': get_company_profile(request)})


@login_required
@require_POST
def save_ollama_settings(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    if body.get('action') == 'reset':
        ollama_session.clear_session_overrides(request)
        return JsonResponse({'ok': True, 'config': ollama_session.get_runtime_config(request)})
    ok, err = ollama_session.save_from_post(request, body)
    if not ok:
        return JsonResponse({'ok': False, 'error': err}, status=400)
    return JsonResponse({'ok': True, 'config': ollama_session.get_runtime_config(request)})


@login_required
@require_GET
def ollama_models_list(request):
    """
    JSON: installed models from Ollama GET /api/tags.
    Optional query: base_url — if omitted, uses session/env effective URL.
    """
    raw = (request.GET.get('base_url') or '').strip()
    if raw:
        base = ollama_session.normalize_base_url(raw)
        if not base:
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'Invalid base_url (use http:// or https://)',
                    'models': [],
                    'base_url': '',
                    'count': 0,
                },
                status=400,
            )
    else:
        base = ollama_session.get_runtime_config(request)['base_url']
    models, err = ollama_session.fetch_installed_models(base)
    if err:
        return JsonResponse(
            {
                'ok': False,
                'error': err,
                'models': models or [],
                'base_url': base,
                'count': len(models or []),
            }
        )
    return JsonResponse(
        {'ok': True, 'models': models, 'base_url': base, 'count': len(models), 'error': None}
    )


@login_required
@require_POST
def regenerate_actuarial_data(request):
    workspace_state.regenerate_actuarial_seed()
    messages.success(
        request,
        'Actuarial dataset regenerated. All views now use new mock values (saved in the database).',
    )
    return redirect(_safe_next_path(request.POST.get('next', '/')))
