"""
CrewAI agent definitions. Pipeline-driven: roles/goals/backstories from session config.
Uses Ollama via crewai.llm.LLM (OpenAI-compatible API at {base}/v1).
"""
from __future__ import annotations

from typing import Any, List

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM
from crewai.llms.base_llm import BaseLLM
from crewai.types.streaming import StreamChunk
from django.conf import settings

from .crew_config import STEP_KINDS_ALLOWED, default_pipeline_copy

# Shape of the leadership deliverable: formal board-paper style (cover metadata + numbered sections + risk table).
BOARD_PAPER_OUTPUT_SPEC = """\
**Mandatory structure** — produce the Board paper as **one** continuous document using Markdown headings. Follow this order:

**Title block (immediately after the `## BOARD PAPER` heading)**
- **Agenda item #:** (number or `TBD` if unknown)
- **Agenda item:** (short title for this paper — derive from the analysis topic / cohort focus)
- **Sponsor:** (name and title if given in organization context; else `TBD — [role]`)

**1. Draft resolution** — Exact or clearly drafted wording of the resolution or decision the board is asked to note or approve (adapt to actuarial context: e.g. note reserving position, risk view, or management actions).

**2. Executive summary** — At most **four short lines** (or one tight paragraph) stating what the paper is about and its objective.

**3. Background** — Context for non-executive readers: scope of the cohort, prior considerations if relevant, external or data caveats (state clearly when figures are **illustrative / mock**).

**4. Recommendation** — Clear recommendation; options considered; preferred outcome. Keep concise (roughly **twelve short lines** or fewer if bullet-style).

**5. Issues**
- **Strategy implications** — How findings align with strategic / business direction.
- **Financial implications** — Reserving, capital, budget, or cash-flow narrative **grounded in the cohort summary** (no invented numbers).

**6. Risk analysis** — A **Markdown table** with exactly these columns:

| Identified risk | Likelihood (H/M/L) | Impact (H/M/L) | Strategy to manage risk |

Include material risks from the analysis (at least **three** rows if risks exist). Use H/M/L only.

**7. Corporate governance and compliance** — Governance and compliance considerations relevant to this paper.

**8. Management responsibility** — Identify the management / executive roles accountable for the proposal (titles; do not invent real people's names unless present in source text).

**9. Signing of board paper** — Placeholder lines only, e.g. *Chief Executive Officer* … *Sponsor* … (no fabricated signatures).

**10. Preparation list** — Bullet list of contributors by **role** (e.g. reserving analysis, risk review); may reference pipeline roles generically.

Integrate prior analyst outputs into this structure; do not append a separate unstructured appendix as the main deliverable.
"""

# Shared discipline for any step whose output is the board pack (live panel + PDF path).
BOARD_OUTPUT_RULES = """\
**Board document output discipline (mandatory):**
- The **first line** of your answer MUST be exactly: `## BOARD PAPER` — then a blank line, then the title block per the spec below. **No words before that line.**
- **Forbidden:** Assistant or chat preambles ("Okay", "Here is", "Below", "complete content as requested", "I will structure", "three labeled sections").
- **Forbidden:** Meta-commentary about prompts, tasks, or how you are organizing the reply.
- **Forbidden in board-facing text:** A/B/C coaching layouts, "What worked / What was wrong" workshop format, or internal coaching headings — those belong only under `### Internal analyst coaching` in the coaching step, not in the board paper.
"""


def build_llm(base_url: str, model: str, temperature: float = 0.2) -> BaseLLM:
    """CrewAI-native LLM pointed at Ollama (must be BaseLLM, not LangChain ChatOllama)."""
    return LLM(
        model=model,
        provider='ollama',
        base_url=base_url.rstrip('/'),
        temperature=temperature,
    )


def get_llm() -> BaseLLM:
    return build_llm(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)


def _task_reserving() -> tuple[str, str]:
    desc = (
        'Review the following actuarial cohort summary (mock session data). '
        'List key facts (numbers, ranges) and 3–6 reserving or development concerns.\n\n'
        '{dataset_summary}'
    )
    return desc, 'Numbered findings: facts, then concerns. No preamble.'


def _task_risk() -> tuple[str, str]:
    return (
        (
            'Using the prior task output and the same cohort context, assess portfolio-level risk: '
            'trend implications, vulnerability interpretation, and which accident years deserve attention.'
        ),
        'Short risk assessment with prioritized watch items (bullet list).',
    )


def _task_initial_report() -> tuple[str, str]:
    return (
        (
            'You are writing **version 1** of one formal **BOARD PAPER** for leadership using the **reserving** and '
            '**risk** analyst outputs already in your context, plus the cohort summary and organization '
            'branding below.\n\n'
            'Cohort summary (ground truth for numbers):\n{dataset_summary}\n\n'
            'Organization / letterhead (use for sponsor line and title block where helpful):\n{company_profile}\n\n'
            'Requirements:\n'
            '- Single continuous document integrating both analyst streams (not separate memos).\n'
            '- Follow the board-paper structure below **exactly** (numbered sections and risk table).\n'
            '- Stay aligned with cohort figures; state when figures are illustrative.\n'
            '- Later pipeline steps will refine this draft—write a complete v1 that already fills every section.\n\n'
            + BOARD_OUTPUT_RULES
            + '\n'
            + BOARD_PAPER_OUTPUT_SPEC
        ),
        (
            'First line exactly `## BOARD PAPER`. Full v1 with sections 1–10; include the risk table; '
            'no invented figures beyond the cohort summary.'
        ),
    )


def _task_executive() -> tuple[str, str]:
    return (
        (
            'You are the **Executive reporting lead** producing **version 2** of the single **BOARD PAPER**.\n\n'
            'You have in context: the **initial report** output (v1 board paper), plus **reserving** and **risk** '
            'analyses, cohort summary, and organization branding.\n\n'
            'Task: Output **one complete updated BOARD PAPER** — not a standalone short memo. Merge the initial '
            'draft into a tightened leadership pack: refresh **Section 2 Executive summary** and ensure sections '
            '1–10 are coherent, consistent, and board-ready; keep the risk table updated; align every figure with '
            'the cohort summary.\n\n'
            'Cohort summary (ground truth):\n{dataset_summary}\n\n'
            'Organization:\n{company_profile}\n\n'
            + BOARD_OUTPUT_RULES
            + '\n'
            + BOARD_PAPER_OUTPUT_SPEC
        ),
        (
            'First line exactly `## BOARD PAPER`. One continuous Markdown document, sections 1–10, full risk table.'
        ),
    )


def _task_manager() -> tuple[str, str]:
    return (
        (
            'Review the full analysis package from the prior tasks (including initial draft, reserving, risk, '
            'executive brief as applicable). Provide: (1) Strengths, (2) Gaps or inconsistencies across tasks, '
            '(3) Leadership-readiness: is the narrative coherent? (4) Recommended edits — without '
            'recalculating metrics yourself.\n\n'
            'Organization context (for report quality):\n{company_profile}'
        ),
        (
            'Structured sections: Strengths; Gaps; Leadership readiness; Recommended edits. '
            'Professional tone, concise.\n\n'
            'Then end with a mandatory section exactly titled:\n'
            '## Workflow handoff\n'
            '- Decision: PROCEED or NEEDS_REWORK\n'
            '- If NEEDS_REWORK: Rework focus (1–3 bullets); Suggested next action (one line, e.g. '
            '"Re-run analysis with topic: …"); Owner hint (human / conceptual role).\n'
            '- If PROCEED: one line why the package can advance.'
        ),
    )


def _task_audit() -> tuple[str, str]:
    return (
        (
            'Audit factual consistency. Use this **source cohort summary** as the ground truth '
            '(compare all numeric ranges, year counts, and labels to this only):\n\n'
            '{dataset_summary}\n\n'
            'Also consider the manager review above. For each notable claim in the reserving, risk, '
            'initial draft, and executive outputs, mark **Pass** if supported by the source summary or **Issue** '
            'if unsupported, contradictory, or imprecise. End with a short risk statement on audit findings.\n\n'
            'Branding reference:\n{company_profile}'
        ),
        (
            'Table or bullet list: Claim / Location (which task) / Pass or Issue / Evidence. '
            'Then Audit summary paragraph.\n\n'
            'Then end with a mandatory section exactly titled:\n'
            '## Workflow handoff\n'
            '- Decision: PROCEED or NEEDS_REWORK\n'
            '- If NEEDS_REWORK: Rework focus; Suggested next action (e.g. "Re-run analysis with topic: …"); '
            'Owner hint.\n'
            '- If PROCEED: one line.'
        ),
    )


def _task_revision() -> tuple[str, str]:
    return (
        (
            '**Revision pass — single BOARD PAPER.** After manager review and audit, you are editing the '
            'one leadership-facing board paper (same artifact viewers see on the live board). Use the audit '
            'Pass/Issue list, manager recommended edits, and the reserving / risk / executive outputs. '
            'Produce a **full updated** board paper in one pass that:\n'
            '- Corrects or qualifies anything flagged in audit (or states why a figure must stay qualified)\n'
            '- Tightens narrative coherence across analyst streams\n'
            '- **Keeps the same board-paper section structure** (sections 1–10 below), including an updated risk table\n'
            '- Stays aligned with this source cohort summary for numbers:\n\n'
            '{dataset_summary}\n\n'
            'Organization branding:\n{company_profile}\n\n'
            + BOARD_OUTPUT_RULES
            + '\n'
            + BOARD_PAPER_OUTPUT_SPEC
            + '\nOutput the **entire** revised board paper (not a side commentary). '
            'After the main document, append **only** the workflow handoff block specified in expected output.'
        ),
        (
            'First line exactly `## BOARD PAPER`. One continuous BOARD PAPER (sections 1–10) per the spec; then a short **Changes vs prior draft** '
            'subsection (bullets) before ## Workflow handoff.\n\n'
            '## Workflow handoff\n'
            '- Decision: PROCEED or NEEDS_REWORK\n'
            '- If NEEDS_REWORK: rework focus; Suggested next action; Owner hint.\n'
            '- If PROCEED: one line.'
        ),
    )


def _task_ceo() -> tuple[str, str]:
    return (
        (
            'You are the **Chief executive officer** signing off for a **human end user** (business reader).\n'
            'Read the **revision** output plus audit and manager context. Your answer must be **short** and '
            'must start with a line the user can scan immediately, for example:\n'
            '- "Approved — you can use this summary as drafted." or\n'
            '- "Approved with conditions — see caveats below." or\n'
            '- "Not ready for reliance — follow the items below first."\n'
            'Then add at most one short paragraph on confidence and residual risk, and bullets only for '
            'material caveats (mock data, unresolved audit issues). No full re-hash of prior tasks.\n\n'
            'Close with ## Workflow handoff: Decision PROCEED or NEEDS_REWORK; if NEEDS_REWORK, name what the '
            'human should redo before the next run.'
        ),
        (
            'Plain-language executive sign-off: handoff line first, then brief rationale, then caveats if any, '
            'then ## Workflow handoff as specified.'
        ),
    )


def _task_coach() -> tuple[str, str]:
    return (
        (
            'This output is **internal workshop feedback only** — it is **not** the board pack and must **never** be '
            'copied verbatim into the board paper or PDF.\n\n'
            'The **first line** of your answer MUST be exactly:\n'
            '### Internal analyst coaching (not for the board pack)\n\n'
            'Do **not** use `## BOARD PAPER` here. Do not write dialogue-style meta text ("Okay", "here is").\n\n'
            'Below that heading, address **A — Reserving analyst**, **B — Risk analyst**, **C — Executive lead** '
            'with bullets under What worked / What was wrong or missing / Do next time.\n'
            'Reference audit, manager, revision, and CEO sign-off where relevant. Tone: constructive.'
        ),
        'Markdown only under the internal coaching heading; A/B/C structure allowed there.',
    )


def _task_final_report() -> tuple[str, str]:
    return (
        (
            'You are the **final audit report author** for the **BOARD PAPER** — the same live document leadership '
            'reviews for approval. Using prior tasks (reserving, risk, executive, manager, audit, revision, CEO '
            'sign-off, and any internal coaching notes), write **one** integrated audited board paper.\n\n'
            'Requirements:\n'
            '- Treat this as the definitive text; refine and supersede earlier draft language from revision where needed.\n'
            '- **Do not** paste A/B/C coaching blocks or "What worked" workshop format into the board paper. If coaching '
            'is in context, fold insights only into narrative findings inside sections 1–10.\n'
            '- **Do not** include the `### Internal analyst coaching` section or its contents in this document.\n'
            '- Follow the board-paper structure below **in full** (audited artifact for human approval).\n'
            '- Stay aligned with cohort figures; state residual caveats in Background as appropriate.\n\n'
            + BOARD_OUTPUT_RULES
            + '\n'
            + BOARD_PAPER_OUTPUT_SPEC
        ),
        (
            'First line exactly `## BOARD PAPER`. Sections 1–10 only (risk table + preparation list); '
            'no coaching appendix; no chat preamble.'
        ),
    )


def _task_generic() -> tuple[str, str]:
    return (
        (
            'Review all prior task outputs in context. Using the cohort summary where needed:\n\n'
            '{dataset_summary}\n\n'
            'Add focused analysis: key takeaways, risks, and recommendations. Stay grounded in the data.'
        ),
        'Clear sections with bullets; no invented figures.',
    )


_TASK_BY_KIND: dict[str, tuple[str, str]] = {
    'reserving': _task_reserving(),
    'risk': _task_risk(),
    'initial_report': _task_initial_report(),
    'executive': _task_executive(),
    'manager': _task_manager(),
    'audit': _task_audit(),
    'revision': _task_revision(),
    'ceo': _task_ceo(),
    'coach': _task_coach(),
    'final_report': _task_final_report(),
    'generic': _task_generic(),
}


def task_description_and_expected(
    step_kind: str,
    dataset_summary_token: str = '{dataset_summary}',
    company_profile_token: str = '{company_profile}',
) -> tuple[str, str]:
    sk = step_kind if step_kind in STEP_KINDS_ALLOWED else 'generic'
    desc, expected = _TASK_BY_KIND[sk]
    if '{dataset_summary}' in desc:
        desc = desc.replace('{dataset_summary}', dataset_summary_token)
    if '{dataset_summary}' in expected:
        expected = expected.replace('{dataset_summary}', dataset_summary_token)
    if '{company_profile}' in desc:
        desc = desc.replace('{company_profile}', company_profile_token)
    if '{company_profile}' in expected:
        expected = expected.replace('{company_profile}', company_profile_token)
    return desc, expected


def build_analysis_crew_from_pipeline(
    ollama_base_url: str,
    default_model: str,
    pipeline: list[dict[str, Any]],
    *,
    task_dataset_text: str = '',
    task_company_text: str = '',
) -> Crew:
    """Build Crew from session pipeline: one Agent and one Task per row; sequential context chain."""
    if not pipeline:
        raise ValueError('pipeline is empty')

    ds_tok = (task_dataset_text or '').strip()
    if not ds_tok:
        ds_tok = (
            '[Full cohort text is in the kickoff input `dataset_summary`; keep outputs consistent with it.]'
        )
    cp_tok = (task_company_text or '').strip()
    if not cp_tok:
        cp_tok = '(No organization branding block was attached to this task; use kickoff context if present.)'

    base = ollama_base_url.rstrip('/')
    agents: list[Agent] = []
    for row in pipeline:
        model = (row.get('ollama_model') or '').strip() or default_model
        llm = build_llm(base, model)
        agents.append(
            Agent(
                role=row['role'],
                goal=row['goal'],
                backstory=row.get('backstory') or '',
                llm=llm,
                verbose=False,
            )
        )

    tasks: list[Task] = []
    for i, row in enumerate(pipeline):
        sk = str(row.get('step_kind') or 'generic').lower()
        desc, expected = task_description_and_expected(sk, ds_tok, cp_tok)
        t = Task(
            description=desc,
            expected_output=expected,
            agent=agents[i],
            context=tasks.copy() if tasks else [],
        )
        tasks.append(t)

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
        stream=True,
    )


def build_analysis_crew(llm: BaseLLM | None = None) -> Crew:
    """Backward-compatible: default eight-step pipeline; optional llm ignored (per-agent LLMs used)."""
    _ = llm
    return build_analysis_crew_from_pipeline(
        settings.OLLAMA_BASE_URL,
        settings.OLLAMA_MODEL,
        default_pipeline_copy(),
    )


def member_ai_labels() -> List[dict[str, str]]:
    """Display strings for legacy member card hints (optional)."""
    return [
        {'id': '1', 'label': 'Reserving analyst (Crew)'},
        {'id': '2', 'label': 'Synthesis lead (Crew)'},
        {'id': '3', 'label': 'Risk analyst (Crew)'},
        {'id': '4', 'label': 'Pricing context'},
        {'id': '5', 'label': 'Systems context'},
        {'id': '6', 'label': 'Compliance context'},
    ]


def chunk_to_event(chunk: StreamChunk) -> dict[str, Any]:
    """Serialize a CrewAI stream chunk to JSON-safe dict."""
    ct = chunk.chunk_type
    ct_str = ct.value if hasattr(ct, 'value') else str(ct)
    ev: dict[str, Any] = {
        'type': 'chunk',
        'task_name': chunk.task_name or '',
        'task_index': int(getattr(chunk, 'task_index', 0) or 0),
        'task_id': getattr(chunk, 'task_id', None) or '',
        'agent_id': getattr(chunk, 'agent_id', None) or '',
        'agent_role': chunk.agent_role or '',
        'content': chunk.content or '',
        'chunk_type': ct_str,
    }
    if chunk.tool_call:
        tc = chunk.tool_call
        ev['tool_name'] = (tc.tool_name or '') if tc else ''
        ev['tool_id'] = (tc.tool_id or '') if tc else ''
        args = (tc.arguments or '') if tc else ''
        ev['tool_arguments_preview'] = args[:500] + ('…' if len(args) > 500 else '')
    return ev
