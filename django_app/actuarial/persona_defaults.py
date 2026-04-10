"""
Default AI persona copy and crew brief (prefill when user has not overridden).
"""
from __future__ import annotations

# Member id -> default "AI persona / priorities" (session roster ids 1–6)
DEFAULT_AI_PERSONA_BY_MEMBER: dict[str, str] = {
    '1': (
        'Lead with reserving rigor: cite loss ratios, development, and reserve adequacy from the summary. '
        'Numbered facts; call out years above target LR. No speculation beyond the cohort text.'
    ),
    '2': (
        'Translate metrics into a crisp narrative for leadership: plain English, short paragraphs, '
        'and explicit call-outs where judgment or external data would still be required in production.'
    ),
    '3': (
        'Emphasize vulnerability scores, trend direction (up/down/stable), and which accident years '
        'warrant monitoring or deeper review.'
    ),
    '4': (
        'Frame observations with pricing and rate-adequacy intuition: focus tags and loss ratio vs premium context.'
    ),
    '5': (
        'Highlight data quality, reproducibility, and systems perspective; keep recommendations actionable for IT/analytics handoff.'
    ),
    '6': (
        'Stress documentation, audit trail, and conservative language suitable for compliance review.'
    ),
}

DEFAULT_GLOBAL_CREW_BRIEF = """Purpose (real operational use): This crew run is not only an internal review—it is to generate a live board report. The leadership-facing draft streams as the pipeline runs and must be suitable for directors and the audit & risk committee: plain language, defensible numbers, and clear asks.

Audience: executive leadership and the quarterly reserving committee; final artifacts should read as if they will sit in the actual board pack alongside governance papers.

Context: Treat the accident-year cohort in the dashboard as our live portfolio. Earned premium, incurred and paid losses, loss ratios, trends, and risk scores are the authoritative numbers for this exercise—work as you would in a real reserving cycle, not a sandbox.

Tone: board-ready, concise, and defensible. Use clear section headings where helpful. Prefer bullets for findings and recommendations. Align narrative with the formal board-paper structure where the pipeline produces it (resolution context, executive summary, risks, governance).

Cover explicitly: (1) performance vs. plan or appetite for loss ratio, if inferable from the cohort; (2) accident years and segments that drive deterioration or improvement; (3) reserve adequacy and development grounded in the figures; (4) material risks, limitations, and data dependencies; (5) vulnerability or concentration themes.

Close with 3–5 prioritized management actions (actuarial, underwriting, claims, or finance as appropriate). Every point should tie to the cohort metrics—no generic commentary."""
