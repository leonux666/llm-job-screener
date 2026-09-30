"""Render the daily digest as HTML."""

from __future__ import annotations

import html
from datetime import date

TIER_LABEL = {1: "Nearby", 2: "Relocation", 3: "Remote"}
VERDICT_COLOR = {
    "strong": "#1a7f37",
    "worth_watching": "#9a6700",
    "stretch": "#8250df",
    "skip": "#6e7781",
    "unclear": "#57606a",
}


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _bar(components: dict | None) -> str:
    """Show where the score came from. A number alone is not auditable."""
    if not components:
        return ""
    order = [("core_technical", 35, "Technical"), ("level_fit", 20, "Level"),
             ("work_type", 15, "Work type"), ("role_quality", 15, "Role"),
             ("required_gaps", -25, "Gaps")]
    cells = []
    for key, maxv, label in order:
        val = components.get(key)
        if val is None:
            continue
        color = "#cf222e" if val < 0 else "#1a7f37"
        cells.append(
            f"<td style='padding:2px 10px 2px 0;white-space:nowrap'>"
            f"<span style='color:#57606a'>{_esc(label)}</span> "
            f"<b style='color:{color}'>{val}</b>"
            f"<span style='color:#8c959f'>/{maxv}</span></td>"
        )
    return (f"<table style='font-size:12px;margin:6px 0 10px'><tr>"
            f"{''.join(cells)}</tr></table>")


def _job_block(j: dict, muted: bool = False) -> str:
    e = j.get("evaluation", {}) or {}
    color = VERDICT_COLOR.get(e.get("verdict", ""), "#57606a")
    tier = TIER_LABEL.get(j.get("location_tier"), "?")

    matches = "".join(f"<li>{_esc(m)}</li>" for m in e.get("matches", [])[:5])
    gaps = "".join(f"<li>{_esc(g)}</li>" for g in e.get("gaps", [])[:5])

    salary = ""
    if e.get("salary_disclosed") and e.get("salary_note"):
        salary = (f"&nbsp;·&nbsp;<span style='color:#1a7f37'>"
                  f"{_esc(e['salary_note'])}</span>")
    elif j.get("salary_min"):
        salary = (f"&nbsp;·&nbsp;<span style='color:#1a7f37'>"
                  f"${int(j['salary_min']):,}–${int(j.get('salary_max') or 0):,}</span>")

    flags = []
    if e.get("insufficient_info"):
        flags.append("posting too vague to evaluate")
    if j.get("title_tier") == "below_target":
        flags.append("title below target tier")
    if e.get("start_date_risk") == "high":
        flags.append("start date conflict")
    flag_html = ""
    if flags:
        flag_html = (f"<div style='margin-top:8px;font-size:13px;color:#bc4c00'>"
                     f"&#9888; {_esc(' · '.join(flags))}</div>")

    pref = ""
    if e.get("preferred_gaps"):
        pref = (f"<div style='font-size:12px;color:#8c959f;margin-top:6px'>"
                f"Preferred but missing (not scored against the candidate): "
                f"{_esc(', '.join(e['preferred_gaps'][:4]))}</div>")

    opacity = "opacity:.75;" if muted else ""

    return f"""
<div style="border:1px solid #d0d7de;border-radius:8px;padding:16px;margin-bottom:16px;{opacity}">
  <div style="font-size:12px;letter-spacing:.5px;text-transform:uppercase;
              color:{color};font-weight:700">
    {_esc(e.get('verdict', 'scored').replace('_', ' '))} &nbsp;·&nbsp; {j.get('score', 0)}/100
  </div>
  <div style="font-size:17px;font-weight:700;margin:4px 0 2px">
    <a href="{_esc(j.get('url'))}" style="color:#0969da;text-decoration:none">
      {_esc(j.get('title'))}</a>
  </div>
  <div style="color:#57606a;font-size:14px;margin-bottom:2px">
    {_esc(j.get('company'))} &nbsp;·&nbsp; {_esc(j.get('location'))}
    &nbsp;·&nbsp; <b>{tier}</b>{salary}
  </div>
  {_bar(e.get('components'))}
  <div style="font-size:14px;line-height:1.5;margin-bottom:10px">
    {_esc(e.get('why'))}
  </div>
  <table style="width:100%;font-size:13px;line-height:1.45">
    <tr style="vertical-align:top">
      <td style="width:50%;padding-right:10px">
        <div style="color:#1a7f37;font-weight:600;margin-bottom:2px">Matches</div>
        <ul style="margin:0;padding-left:18px">{matches or '<li>&mdash;</li>'}</ul>
      </td>
      <td style="width:50%">
        <div style="color:#cf222e;font-weight:600;margin-bottom:2px">Required, not met</div>
        <ul style="margin:0;padding-left:18px">{gaps or '<li>&mdash;</li>'}</ul>
      </td>
    </tr>
  </table>
  {pref}
  {flag_html}
  <div style="margin-top:10px;padding-top:10px;border-top:1px solid #eaeef2;
              font-size:13px;color:#57606a">
    <b>Signal:</b> {_esc(e.get('signal'))}
  </div>
</div>"""


def _drops_line(drops: dict[str, int]) -> str:
    if not drops:
        return ""
    veto = {k.replace("deal-breaker: ", ""): v for k, v in drops.items()
            if k.startswith("deal-breaker")}
    if not veto:
        return ""
    parts = ", ".join(f"{k} ({v})" for k, v in sorted(veto.items(),
                                                      key=lambda kv: -kv[1]))
    return (f"<p style='color:#8c959f;font-size:12px;margin:0 0 20px'>"
            f"Vetoed before scoring: {html.escape(parts)}</p>")


def render(jobs: list[dict], near_misses: list[dict], stats: dict) -> str:
    if jobs:
        body = "".join(_job_block(j) for j in jobs)
    elif near_misses:
        body = (
            "<p style='color:#57606a'>Nothing cleared the score threshold. The "
            f"{len(near_misses)} closest are below. If these read as the wrong "
            "<i>kinds</i> of companies rather than near-fits, the source list is "
            "the problem, not the threshold.</p>"
            + "".join(_job_block(j, muted=True) for j in near_misses)
        )
    else:
        body = ("<p style='color:#57606a'>Nothing scored today. Either no new "
                "postings cleared the keyword gate, or every source returned "
                "empty &mdash; check the log before assuming it was a quiet day.</p>")

    # Optional free-text line from `report.footer_note` in config.yaml, for
    # standing context that applies to every digest — an availability date, a
    # reminder of what the digest is for. Omitted entirely when unset.
    note = (stats.get("footer_note") or "").strip()
    note_html = f"{html.escape(note)}\n    " if note else ""

    closed = stats.get("closed", 0)
    closed_html = ""
    if closed:
        med = stats.get("median_days_open")
        med_txt = f", median {med} days open" if med is not None else ""
        closed_html = (f" &nbsp;·&nbsp; {closed} req{'s' if closed != 1 else ''} "
                       f"closed{med_txt}")

    return f"""<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
      max-width:720px;margin:0 auto;padding:20px;color:#1f2328">
  <h2 style="margin:0 0 4px">Job scan &mdash; {date.today().isoformat()}</h2>
  <p style="color:#57606a;font-size:13px;margin:0 0 6px">
    {stats.get('fetched', 0)} fetched &nbsp;·&nbsp;
    {stats.get('new', 0)} new &nbsp;·&nbsp;
    {stats.get('filtered', 0)} passed gate &nbsp;·&nbsp;
    {stats.get('scored', 0)} deep-scored &nbsp;·&nbsp;
    {len(jobs)} reported{closed_html}
  </p>
  {_drops_line(stats.get('drops', {}))}
  {body}
  <p style="color:#8c959f;font-size:12px;border-top:1px solid #eaeef2;
            padding-top:12px;margin-top:24px">
    {note_html}Run <code>python -m agent.upskill</code> once a month to see which
    missing skills keep blocking the best-scoring roles.
  </p>
</body></html>"""
