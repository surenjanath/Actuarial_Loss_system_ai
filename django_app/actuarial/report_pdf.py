"""
Build stored PDF bytes for an approved crew run (fpdf2).
Renders board-paper style Markdown: headings, bullets, and pipe tables (e.g. risk analysis).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fpdf import FPDF
from fpdf.enums import Align

if TYPE_CHECKING:
    from .models import CrewRun

_RE_MD_SEP_ROW = re.compile(r'^\|[\s\-:|]+\|\s*$')
_RE_HEADING = re.compile(r'^(#{1,6})\s+(.+)$')


def _core_font_text(s: str) -> str:
    """Helvetica only supports Latin-1; normalize common Unicode punctuation."""
    if not s:
        return ''
    t = str(s)
    for a, b in (
        ('\u2014', '-'),
        ('\u2013', '-'),
        ('\u2026', '...'),
        ('\u2018', "'"),
        ('\u2019', "'"),
        ('\u201c', '"'),
        ('\u201d', '"'),
    ):
        t = t.replace(a, b)
    return t.encode('latin-1', 'replace').decode('latin-1')


def _strip_md_emphasis(s: str) -> str:
    """Remove ** and __ for PDF core font output; keeps inner text."""
    t = s.replace('**', '').replace('__', '')
    return t.strip()


def _split_table_line(line: str) -> list[str]:
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    return [c.strip() for c in s.split('|')]


def _is_table_separator_row(line: str) -> bool:
    s = line.strip()
    if not s.startswith('|'):
        return False
    if _RE_MD_SEP_ROW.match(s):
        return True
    inner = _split_table_line(s if s.startswith('|') else '|' + s)
    if not inner:
        return False
    return all(re.match(r'^:?-+:?$', cell.replace(' ', '')) for cell in inner if cell)


def _parse_table_block(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for ln in lines:
        if _is_table_separator_row(ln):
            continue
        cells = _split_table_line(ln)
        if cells:
            rows.append(cells)
    return rows


def _emit_heading(pdf: FPDF, text_w: float, level: int, text: str) -> None:
    plain = _core_font_text(_strip_md_emphasis(text))
    if level == 1:
        pdf.set_font('Helvetica', 'B', 16)
        pdf.multi_cell(text_w, 7, plain)
    elif level == 2:
        pdf.set_font('Helvetica', 'B', 12)
        pdf.ln(1)
        pdf.multi_cell(text_w, 6, plain)
    else:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.ln(0.5)
        pdf.multi_cell(text_w, 5, plain)
    pdf.set_font('Helvetica', '', 10)
    pdf.ln(1)


def _emit_table(pdf: FPDF, text_w: float, rows: list[list[str]]) -> None:
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    # Normalize row lengths
    norm: list[list[str]] = []
    for r in rows:
        padded = [_core_font_text(_strip_md_emphasis(c)) for c in r]
        while len(padded) < ncols:
            padded.append('')
        norm.append(padded[:ncols])
    # Column width fractions (equal); fpdf interprets tuple as fractions of table width
    fracs = tuple([1] * ncols)
    pdf.ln(1)
    with pdf.table(
        width=text_w,
        align=Align.L,
        col_widths=fracs,
        text_align=Align.L,
        line_height=6,
        padding=3,
        gutter_height=0,
        gutter_width=1,
        first_row_as_headings=True,
        borders_layout='ALL',
    ) as table:
        for row_cells in norm:
            table.row(row_cells)
    pdf.ln(2)
    pdf.set_font('Helvetica', '', 10)


def _trim_duplicate_cover_title(body: str) -> str:
    """If the report repeats 'BOARD PAPER' on line 1, drop it (cover already shows the title)."""
    lines = body.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return body
    first = _strip_md_emphasis(lines[i].strip())
    if first.upper().rstrip('.') == 'BOARD PAPER':
        lines = lines[i + 1 :]
        while lines and not lines[0].strip():
            lines = lines[1:]
        return '\n'.join(lines)
    return body


def render_markdownish_report_body(pdf: FPDF, body: str, text_w: float) -> None:
    """
    Line-oriented Markdown: ATX headings (#), bullet lines, pipe tables, paragraphs.
    """
    raw = _trim_duplicate_cover_title((body or '').strip())
    if not raw:
        pdf.set_font('Helvetica', '', 10)
        pdf.multi_cell(text_w, 5, '(No report text.)')
        return

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            pdf.ln(2)
            i += 1
            continue

        # Pipe table block (GitHub-flavored)
        if stripped.startswith('|') and '|' in stripped[1:]:
            block: list[str] = []
            j = i
            while j < len(lines) and lines[j].strip().startswith('|'):
                block.append(lines[j])
                j += 1
            rows = _parse_table_block(block)
            if rows and len(rows[0]) >= 2:
                _emit_table(pdf, text_w, rows)
                i = j
                continue

        hm = _RE_HEADING.match(stripped)
        if hm:
            level = len(hm.group(1))
            title = hm.group(2).strip()
            _emit_heading(pdf, text_w, level, title)
            i += 1
            continue

        if stripped == '---' or stripped == '***':
            pdf.set_draw_color(120, 120, 120)
            pdf.set_line_width(0.2)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y + 2, pdf.w - pdf.r_margin, y + 2)
            pdf.set_draw_color(0, 0, 0)
            pdf.ln(4)
            i += 1
            continue

        if stripped.startswith('- ') or stripped.startswith('* '):
            pdf.set_x(pdf.l_margin + 3)
            pdf.set_font('Helvetica', '', 10)
            bullet = '- ' + _core_font_text(_strip_md_emphasis(stripped[2:]))
            pdf.multi_cell(text_w - 3, 5, bullet)
            i += 1
            continue

        # Numbered list "1. foo"
        num_m = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_m:
            pdf.set_x(pdf.l_margin + 3)
            pdf.set_font('Helvetica', '', 10)
            para = f"{num_m.group(1)}. {_core_font_text(_strip_md_emphasis(num_m.group(2)))}"
            pdf.multi_cell(text_w - 3, 5, para)
            i += 1
            continue

        pdf.set_font('Helvetica', '', 10)
        pdf.multi_cell(text_w, 5, _core_font_text(_strip_md_emphasis(stripped)))
        i += 1


def _org_header_lines() -> list[str]:
    from .models import OrganizationProfile

    row = OrganizationProfile.objects.filter(pk=1).first()
    if not row:
        return []
    lines: list[str] = []
    if row.company_name.strip():
        lines.append(row.company_name.strip())
    if row.legal_name.strip() and row.legal_name.strip() != row.company_name.strip():
        lines.append(row.legal_name.strip())
    if row.tagline.strip():
        lines.append(row.tagline.strip())
    parts = [x for x in (row.address, row.city, row.region, row.postal_code, row.country) if x and str(x).strip()]
    if parts:
        lines.append(', '.join(str(p).strip() for p in parts))
    return lines


def build_approved_report_pdf_bytes(run: CrewRun) -> bytes:
    """Return PDF file bytes; raises on fpdf2 errors."""
    body = (run.final_report_text or '').strip()
    if not body:
        body = '(No report text.)'

    pdf = FPDF()
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    text_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Cover / title block
    pdf.set_font('Helvetica', 'B', 20)
    pdf.cell(text_w, 10, 'BOARD PAPER', ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(text_w, 5, 'Approved actuarial crew report', ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_font('Helvetica', '', 9)
    org_lines = _org_header_lines()
    for line in org_lines:
        line = _core_font_text((line or '').strip())
        if not line:
            continue
        pdf.multi_cell(text_w, 5, line)
    if org_lines:
        pdf.ln(2)

    pdf.set_font('Helvetica', 'I', 8)
    topic = _core_font_text((run.topic or '').strip()) or '-'
    meta = _core_font_text(
        f'Run ID: {run.id}\n'
        f'Topic / focus: {topic}\n'
        f'Approved: {run.approved_at.isoformat() if run.approved_at else "-"}\n'
        f'Model: {run.ollama_model or "-"}'
    )
    pdf.multi_cell(text_w, 4, meta)
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(text_w, 6, 'Report', ln=True)
    pdf.ln(1)
    pdf.set_font('Helvetica', '', 10)

    render_markdownish_report_body(pdf, body, text_w)

    out = pdf.output()
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, bytes):
        return out
    return str(out).encode('latin-1', 'replace')
