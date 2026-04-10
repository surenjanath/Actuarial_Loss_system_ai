"""
Parse agent "Workflow handoff" blocks from step text (PROCEED / NEEDS_REWORK).
"""
from __future__ import annotations

import re
from typing import Any

_HANDOFF_STEP_KINDS = frozenset({'manager', 'audit', 'revision', 'ceo'})


def summarize_handoff_from_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Scan latest handoff-capable steps for NEEDS_REWORK and optional suggested topic.
    """
    out: dict[str, Any] = {
        'needs_rework': False,
        'source_step_kind': '',
        'snippet': '',
        'prefill_topic': '',
    }
    if not steps:
        return out
    by_idx = sorted(steps, key=lambda s: int(s.get('step_index', 0)), reverse=True)
    for s in by_idx:
        sk = str(s.get('step_kind') or '').lower()
        if sk not in _HANDOFF_STEP_KINDS:
            continue
        content = (s.get('content') or '').strip()
        if not content:
            continue
        if not re.search(r'NEEDS[_\s-]?REWORK', content, re.IGNORECASE):
            continue
        out['needs_rework'] = True
        out['source_step_kind'] = sk
        # Extract workflow section if present
        msec = re.search(
            r'##\s*Workflow handoff\s*(.*?)(?:\Z|(?=##\s))',
            content,
            re.DOTALL | re.IGNORECASE,
        )
        snippet = (msec.group(1).strip() if msec else content)[:1200]
        if len((msec.group(1) if msec else content)) > 1200:
            snippet += '\n…'
        out['snippet'] = snippet
        # Topic lines: "Re-run analysis with topic: foo" or "Suggested next action" bullet
        topic = ''
        tm = re.search(
            r'Re-run analysis with topic:\s*([^\n]+)',
            content,
            re.IGNORECASE,
        )
        if tm:
            topic = tm.group(1).strip()
        if not topic:
            tm2 = re.search(
                r'Suggested next action:\s*([^\n]+)',
                content,
                re.IGNORECASE,
            )
            if tm2:
                topic = tm2.group(1).strip()[:500]
        out['prefill_topic'] = topic
        break
    return out
