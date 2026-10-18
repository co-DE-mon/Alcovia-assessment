"""HTML building blocks for the dashboard. Pure functions with no Streamlit import, so they can be tested.

Rules (from the dataviz guidance): a status is never shown by colour alone (icon + label); text uses the page's own ink so markup works in light and
dark themes; every value goes through html.escape; markup is built on one line because Markdown treats indented HTML as code.
"""
from html import escape as e

import fmt

STATUS = {   # label, icon glyph, soft fill, ink (dark text on a tint, so the label stays readable; the icon and word carry the meaning)
    "on_track": ("On track", "✓", "#dff1e7", "#1d5e3f"),
    "watch": ("Watch", "!", "#faeccb", "#6e4f00"),
    "off_track": ("Off track", "✕", "#f8dede", "#8f2b2b"),
    "no_data": ("No data", "–", "#e8ecf2", "#46526a"),
}
CSS = """<style>
.stApp { background: #f4f6fa; color: #2a3a4d; }
[data-testid="stToolbar"], .stAppDeployButton, [data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: none !important; padding: 2.6rem 2.5rem 3rem !important; }
[data-testid="stPageLink"] { margin-top: 2px; }
[data-testid="stPageLink"]:first-of-type { margin-top: 22px; }
[data-testid="stHorizontalBlock"] { margin-bottom: 1.4rem; }
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"], .stVegaLiteChart { margin: 1rem 0; }
[data-testid="stExpander"] { margin-top: .8rem; }
[data-testid="stDataFrame"] { margin: .4rem 0 .8rem; }
.gt-banner { display: inline-block; background: #fdf3da; border: 1px solid #f0e0b0; color: #6b5200; padding: 4px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 8px; }
.gt-title { font-size: 34px; font-weight: 600; letter-spacing: -0.02em; margin: 4px 0 2px; padding: 0; color: #2a3a4d; }
.gt-blurb { font-size: 15px; color: #5d6b7c; margin: 0 0 14px; max-width: 70ch; }
.gt-h2 { font-size: 22px; font-weight: 600; margin: 30px 0 2px; padding: 0; color: #2a3a4d; }
.gt-sub-h { font-size: 14px; color: #5d6b7c; margin: 0 0 10px; max-width: 75ch; }
.gt-span { font-size: 14px; color: #5d6b7c; padding-top: 34px; font-variant-numeric: tabular-nums; }
.gt-tile { background: #fff; border: 1px solid #e3e8ef; border-radius: 10px; padding: 14px 16px; min-height: 128px; box-shadow: 0 1px 2px rgba(30,50,80,.04); }
.gt-label { font-size: 13px; color: #5d6b7c; }
.gt-value { font-size: 34px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.15; margin-top: 2px; font-variant-numeric: tabular-nums; color: #2a3a4d; }
.gt-sub { font-size: 13px; color: #5d6b7c; margin-top: 4px; }
.gt-status { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.gt-meter { height: 14px; background: #e9eef5; border-radius: 7px; margin-top: 14px; overflow: hidden; }
.gt-meter-fill { height: 100%; background: #6b97d4; border-radius: 7px; }
.gt-meter-text, .gt-meter-note { font-size: 14px; color: #5d6b7c; margin-top: 6px; font-variant-numeric: tabular-nums; }
.gt-table { margin-top: .4rem; width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e3e8ef; border-radius: 10px; font-size: 14px; font-variant-numeric: tabular-nums; }
.gt-table th { text-align: left; font-weight: 600; color: #5d6b7c; padding: 8px 12px; border-bottom: 1px solid #e3e8ef; background: #f8f9fc; }
.gt-table td { vertical-align: top; padding: 8px 12px; border-bottom: 1px solid #f0f3f7; color: #2a3a4d; }
.gt-table tr:last-child td { border-bottom: none; }
.gt-facts { display: grid; grid-template-columns: 9rem 1fr; gap: 6px 14px; background: #fff; border: 1px solid #e3e8ef; border-radius: 10px; padding: 14px 16px; margin: 0; font-size: 14px; }
.gt-facts dt { color: #5d6b7c; }
.gt-facts dd { margin: 0; color: #2a3a4d; font-variant-numeric: tabular-nums; }
.gt-list { margin: 0; padding-left: 1.1rem; }
.gt-list li { margin: 0 0 4px; }
.gt-verdicts td:nth-child(2) { min-width: 9rem; }
.gt-empty { background: #fff; border: 1px dashed #cdd5df; border-radius: 10px; padding: 16px; color: #5d6b7c; font-size: 14px; }
@media (max-width: 760px) { .gt-value { font-size: 26px; } .gt-title { font-size: 28px; } .gt-table { display: block; overflow-x: auto; } }
</style>"""


def banner():
    return '<div class="gt-banner"><b>Dummy data</b> · every number here is generated for the assessment; nothing is real.</div>'


def tile(label, value, sub=None, status=None):
    """A headline number with its label; an optional sub-line and an optional status (icon + word, never colour alone)."""
    badge = ""
    if status:
        text, icon, fill, ink = STATUS[status]
        badge = f'<span class="gt-status" style="background:{fill};color:{ink}">{e(icon)} {e(text)}</span>'
    sub_html = f'<div class="gt-sub">{e(str(sub))}</div>' if sub else ""
    return f'<div class="gt-tile"><div class="gt-label">{e(str(label))}</div><div class="gt-value">{e(str(value))}</div>{sub_html}{badge}</div>'


def facts(pairs):
    """A two-column list of label and value pairs (a missing value shows a dash). pairs = [(label, value)]; everything is escaped."""
    items = "".join(f"<dt>{e(label)}</dt><dd>{e(fmt.DASH if fmt.missing(value) else str(value))}</dd>" for label, value in pairs)
    return f'<dl class="gt-facts">{items}</dl>'


VERDICT_STATUS = {"Scale": "on_track", "Hold": "watch", "Refresh": "watch", "Pause": "off_track", "Too early": "no_data"}


def verdict_chip(verdict, label=None):
    """A verdict as a chip: icon and words in the fixed status colours. `label` is the longer wording (for example Hold: recent acquisition cost worsening)."""
    return chip(label or verdict, VERDICT_STATUS[verdict])


def verdict_table(rows):
    """The RCA table: campaign, verdict, why, flags and evidence in separate columns. rows are dicts from rca.py (campaign_id, name, verdict, label, reasons, flags, confidence).
    Every text is escaped; the chip is built here, so it is the only markup that is not."""
    if not rows:
        return '<div class="gt-empty">Nothing to show for this period.</div>'
    def items(texts):
        return '<ul class="gt-list">' + "".join(f"<li>{e(str(t))}</li>" for t in texts) + "</ul>" if texts else fmt.DASH
    body = "".join(f"<tr><td><b>{e(str(r['campaign_id']))}</b><br>{e(str(r['name']))}</td><td>{verdict_chip(r['verdict'], r['label'])}</td>"
                   f"<td>{items(r['reasons'])}</td><td>{items(r['flags'])}</td><td>{e(str(r['confidence']))}</td></tr>" for r in rows)
    return f'<table class="gt-table gt-verdicts"><thead><tr><th>Campaign</th><th>Verdict</th><th>Why</th><th>Flags</th><th>Evidence</th></tr></thead><tbody>{body}</tbody></table>'


def chip(text, status):
    """A small status label: icon + words in the fixed status colour."""
    _, icon, fill, ink = STATUS[status]
    return f'<span class="gt-status" style="background:{fill};color:{ink}">{e(icon)} {e(str(text))}</span>'


def meter(value, target, label="Achieved"):
    """A track filled to value/target (capped at 100%), with the real share written out. No target gives a plain note instead of a bar."""
    if fmt.missing(target) or not target:
        return '<div class="gt-meter-note">No target set for this period.</div>'
    share = value / target
    width = min(100, max(0, share * 100))
    return (f'<div class="gt-meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{round(share * 100)}" aria-label="{e(label)}">'
            f'<div class="gt-meter-fill" style="width:{width:.0f}%"></div></div><div class="gt-meter-text">{e(label)} {share * 100:.0f}% of target</div>')


def table(rows, columns):
    """An HTML table. columns = [(key, heading, formatter or None)]; a formatter turns a raw value into text (escaped here), None shows str(value)."""
    if not rows:
        return '<div class="gt-empty">Nothing to show for this period.</div>'
    head = "".join(f"<th>{e(h)}</th>" for _, h, _ in columns)
    body = ""
    for row in rows:
        cells = ""
        for key, _, formatter in columns:
            value = row.get(key)
            cells += f"<td>{e(formatter(value) if formatter else (fmt.DASH if fmt.missing(value) else str(value)))}</td>"
        body += f"<tr>{cells}</tr>"
    return f'<table class="gt-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
