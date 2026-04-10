"""
Port of src/data/actuarialData.ts — mock actuarial data and helpers.
Uses a database-stored RNG seed (WorkspaceState) so all clients see the same dataset.
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Literal, TypedDict


class ActuarialYear(TypedDict):
    id: str
    accident_year: int
    reported_claims: int
    paid_losses: int
    incurred_losses: int
    earned_premium: int
    loss_ratio: float
    reserve_adequacy: float
    development_factor: float
    trend: Literal['up', 'down', 'stable']
    risk_score: float


class TeamMember(TypedDict):
    id: str
    name: str
    role: str
    department: str
    status: Literal['active', 'busy', 'offline', 'in-meeting']
    avatar: str
    tasks_completed: int
    efficiency: int
    specialization: List[str]


def ensure_actuarial_seed(request) -> int:
    """Stable random seed for mock actuarial data (persisted in WorkspaceState)."""
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    return workspace_state.ensure_actuarial_seed_in_db()


def rng_for_request(request) -> random.Random:
    return random.Random(ensure_actuarial_seed(request))


def generate_actuarial_data(rng: random.Random) -> List[ActuarialYear]:
    years: List[ActuarialYear] = []
    base_year = 2014
    for i in range(10):
        year = base_year + i
        base_premium = 50000000 + (i * 3000000) + (rng.random() * 2000000)
        loss_ratio_base = 0.65 + (math.sin(i * 0.8) * 0.15) + (rng.random() * 0.1)
        incurred_losses = base_premium * loss_ratio_base
        paid_losses = incurred_losses * (0.7 + (i * 0.02) + (rng.random() * 0.1))
        reported_claims = int(800 + (i * 50) + (rng.random() * 200))

        trend: Literal['up', 'down', 'stable'] = 'stable'
        if i > 0:
            prev_loss_ratio = years[i - 1]['loss_ratio']
            if loss_ratio_base > prev_loss_ratio + 0.05:
                trend = 'up'
            elif loss_ratio_base < prev_loss_ratio - 0.05:
                trend = 'down'

        risk_score = round(loss_ratio_base * 100 + (rng.random() * 20), 1)

        row: ActuarialYear = {
            'id': f'year-{year}',
            'accident_year': year,
            'reported_claims': reported_claims,
            'paid_losses': round(paid_losses),
            'incurred_losses': round(incurred_losses),
            'earned_premium': round(base_premium),
            'loss_ratio': round(loss_ratio_base, 4),
            'reserve_adequacy': round(0.85 + (rng.random() * 0.3), 2),
            'development_factor': round(1.1 + (rng.random() * 0.4), 3),
            'trend': trend,
            'risk_score': risk_score,
        }
        years.append(row)

    return years


def calculate_vulnerability_probability(
    actuarial_data: List[ActuarialYear],
    target_loss_ratio: float,
    weight_incurred: float = 0.4,
    weight_trend: float = 0.3,
    weight_reserve: float = 0.3,
) -> List[float]:
    out: List[float] = []
    for y in actuarial_data:
        loss_ratio_score = min(100, (y['loss_ratio'] / target_loss_ratio) * 50)
        if y['trend'] == 'up':
            trend_score = 30.0
        elif y['trend'] == 'stable':
            trend_score = 15.0
        else:
            trend_score = 5.0
        reserve_score = min(50, (1 / y['reserve_adequacy']) * 40)
        v = (
            loss_ratio_score * weight_incurred
            + trend_score * weight_trend
            + reserve_score * weight_reserve
        )
        out.append(round(v, 2))
    return out


def format_currency(value: float) -> str:
    return f'${value:,.0f}'


def format_number(value: float | int) -> str:
    return f'{int(round(value)):,}'


def format_percentage(value: float) -> str:
    return f'{(value * 100):.2f}%'


def get_team_members() -> List[TeamMember]:
    return [
        {
            'id': '1',
            'name': 'Andrew Sabato',
            'role': 'Chief Actuary',
            'department': 'Analytics',
            'status': 'active',
            'avatar': 'AS',
            'tasks_completed': 847,
            'efficiency': 94,
            'specialization': ['Loss Reserving', 'Predictive Modeling', 'Risk Assessment'],
        },
        {
            'id': '2',
            'name': 'Sarah Chen',
            'role': 'Senior Data Scientist',
            'department': 'Data Science',
            'status': 'busy',
            'avatar': 'SC',
            'tasks_completed': 623,
            'efficiency': 91,
            'specialization': ['Machine Learning', 'Statistical Analysis', 'Python'],
        },
        {
            'id': '3',
            'name': 'Marcus Johnson',
            'role': 'Risk Analyst',
            'department': 'Risk Management',
            'status': 'active',
            'avatar': 'MJ',
            'tasks_completed': 512,
            'efficiency': 88,
            'specialization': ['Catastrophe Modeling', 'Reinsurance', 'Capital Modeling'],
        },
        {
            'id': '4',
            'name': 'Emily Rodriguez',
            'role': 'Actuarial Associate',
            'department': 'Pricing',
            'status': 'in-meeting',
            'avatar': 'ER',
            'tasks_completed': 389,
            'efficiency': 86,
            'specialization': ['Pricing Models', 'GLM', 'R'],
        },
        {
            'id': '5',
            'name': 'David Park',
            'role': 'Systems Architect',
            'department': 'IT',
            'status': 'active',
            'avatar': 'DP',
            'tasks_completed': 756,
            'efficiency': 92,
            'specialization': ['Cloud Infrastructure', 'Security', 'DevOps'],
        },
        {
            'id': '6',
            'name': 'Lisa Thompson',
            'role': 'Compliance Officer',
            'department': 'Legal',
            'status': 'offline',
            'avatar': 'LT',
            'tasks_completed': 445,
            'efficiency': 89,
            'specialization': ['Regulatory Compliance', 'Audit', 'Documentation'],
        },
    ]


def actuarial_rows_for_js_dashboard(rows: List[ActuarialYear]) -> List[dict[str, Any]]:
    """Full row data for dashboard interactivity (camelCase for json_script)."""
    return [
        {
            'id': r['id'],
            'accidentYear': r['accident_year'],
            'reportedClaims': r['reported_claims'],
            'paidLosses': r['paid_losses'],
            'incurredLosses': r['incurred_losses'],
            'earnedPremium': r['earned_premium'],
            'lossRatio': r['loss_ratio'],
            'reserveAdequacy': r['reserve_adequacy'],
            'trend': r['trend'],
            'riskScore': r['risk_score'],
            'developmentFactor': r['development_factor'],
        }
        for r in rows
    ]


def particle_rows_for_js(rows: List[ActuarialYear]) -> List[dict[str, Any]]:
    return [{'accidentYear': r['accident_year'], 'lossRatio': r['loss_ratio']} for r in rows]


def chart_data_for_js(rows: List[ActuarialYear]) -> List[dict[str, Any]]:
    return [
        {
            'year': r['accident_year'],
            'incurred': r['incurred_losses'],
            'paid': r['paid_losses'],
            'premium': r['earned_premium'],
            'lossRatio': r['loss_ratio'] * 100,
            'claims': r['reported_claims'],
            'reserve': r['reserve_adequacy'],
        }
        for r in rows
    ]


def dashboard_metrics(
    actuarial_data: List[ActuarialYear],
    vulnerability_probabilities: List[float],
    target_loss_ratio: float = 0.68,
) -> dict[str, Any]:
    n = len(actuarial_data)
    total_incurred = sum(y['incurred_losses'] for y in actuarial_data)
    total_premium = sum(y['earned_premium'] for y in actuarial_data)
    avg_loss_ratio = sum(y['loss_ratio'] for y in actuarial_data) / n if n else 0.0
    avg_vulnerability = (
        sum(vulnerability_probabilities) / len(vulnerability_probabilities)
        if vulnerability_probabilities
        else 0.0
    )
    total_claims = sum(y['reported_claims'] for y in actuarial_data)
    incurred_pct_premium = (total_incurred / total_premium) * 100 if total_premium else 0.0
    years_above_target = sum(1 for y in actuarial_data if y['loss_ratio'] > target_loss_ratio)
    trend_up = sum(1 for y in actuarial_data if y['trend'] == 'up')
    trend_down = sum(1 for y in actuarial_data if y['trend'] == 'down')
    trend_stable = sum(1 for y in actuarial_data if y['trend'] == 'stable')
    lr_low = min((y['loss_ratio'] for y in actuarial_data), default=0.0)
    lr_high = max((y['loss_ratio'] for y in actuarial_data), default=0.0)
    high_vulnerability_years = sum(1 for v in vulnerability_probabilities if v > 50.0)
    max_v = max(vulnerability_probabilities) if vulnerability_probabilities else 0.0
    min_v = min(vulnerability_probabilities) if vulnerability_probabilities else 0.0
    return {
        'total_incurred': total_incurred,
        'total_premium': total_premium,
        'avg_loss_ratio': avg_loss_ratio,
        'avg_vulnerability': avg_vulnerability,
        'total_claims': total_claims,
        'years_analyzed': n,
        'incurred_pct_premium': incurred_pct_premium,
        'years_above_target': years_above_target,
        'trend_up': trend_up,
        'trend_down': trend_down,
        'trend_stable': trend_stable,
        'lr_range_low': lr_low,
        'lr_range_high': lr_high,
        'high_vulnerability_years': high_vulnerability_years,
        'max_vulnerability': max_v,
        'min_vulnerability': min_v,
    }


def statistics_summary(rows: List[ActuarialYear]) -> dict[str, Any]:
    total_premium = sum(y['earned_premium'] for y in rows)
    total_incurred = sum(y['incurred_losses'] for y in rows)
    avg_loss_ratio = sum(y['loss_ratio'] for y in rows) / len(rows)
    growth_rate = (
        (rows[-1]['earned_premium'] - rows[0]['earned_premium']) / rows[0]['earned_premium']
    ) * 100
    total_claims = sum(y['reported_claims'] for y in rows)
    incurred_pct_premium = (
        (total_incurred / total_premium) * 100 if total_premium else 0.0
    )
    return {
        'total_premium': total_premium,
        'total_incurred': total_incurred,
        'avg_loss_ratio': avg_loss_ratio,
        'growth_rate': growth_rate,
        'total_claims': total_claims,
        'first_year': rows[0]['accident_year'],
        'last_year': rows[-1]['accident_year'],
        'claims_avg_per_year': total_claims / len(rows),
        'incurred_pct_premium': incurred_pct_premium,
    }


# Column order for CSV export (matches ActuarialYear)
ACTUARIAL_EXPORT_FIELDS: tuple[str, ...] = (
    'id',
    'accident_year',
    'reported_claims',
    'paid_losses',
    'incurred_losses',
    'earned_premium',
    'loss_ratio',
    'reserve_adequacy',
    'development_factor',
    'trend',
    'risk_score',
)


def actuarial_rows_for_api(rows: List[ActuarialYear]) -> List[dict[str, Any]]:
    """Plain dicts for JSON serialization."""
    return [dict(r) for r in rows]


TEAM_EXPORT_FIELDS: tuple[str, ...] = (
    'id',
    'name',
    'role',
    'department',
    'status',
    'tasks_completed',
    'efficiency',
    'specialization',
)
