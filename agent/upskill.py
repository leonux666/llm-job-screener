"""Turn the accumulated job log into a learning priority list.

    python -m agent.upskill              console table
    python -m agent.upskill --html       also writes upskill.html

The question this answers is not "which skills am I missing" — the profile
already lists those. It is "which missing skills are blocking the roles I
actually want", which is a different and much shorter list.

Two counts are reported per tag, and the difference between them is the point:

- **Frequency** — how many postings named it as required. A skill can be common
  and still irrelevant if it only appears in roles that were poor fits anyway.
- **Blocked score** — the total points lost across postings, weighted by how
  well the posting scored otherwise. A gap that costs eight points on a posting
  that would have scored 85 matters far more than the same gap on one that
  would have scored 40.

Sort by blocked score, not frequency. That column is the curriculum.
"""

from __future__ import annotations

import argparse
import collections
import html
import statistics
from datetime import date, datetime, timedelta

from agent import state

TAG_LABEL = {
    "ml": "Machine learning",
    "deep-learning": "Deep learning",
    "single-cell": "Single-cell RNA-seq (Seurat/Scanpy)",
    "spatial-omics": "Spatial omics",
    "sql": "SQL / relational databases",
    "cloud": "Cloud platforms (AWS/GCP)",
    "docker": "Containers (Docker/Singularity)",
    "nextflow-workflow": "Workflow managers (Nextflow/Snakemake)",
    "shotgun-metagenomics": "Shotgun metagenomics",
    "proteomics": "Proteomics",
    "mass-spec": "Mass spectrometry",
    "variant-calling": "Variant calling",
    "population-genetics": "Population genetics",
    "clinical-genomics": "Clinical genomics",
    "imaging-analysis": "Imaging analysis",
    "software-engineering": "Software engineering practice",
    "gmp-glp": "GMP / GLP environments",
    "protein-chemistry": "Protein analytical chemistry",
    "human-subjects": "Human subjects work",
    "wet-lab-technique": "Specific wet-lab technique",
    "project-management": "Formal project management",
    "other": "Other",
}


def analyse(rows: list[dict], since_days: int | None = None) -> dict:
    if since_days:
        cutoff = (date.today() - timedelta(days=since_days)).isoformat()
        rows = [r for r in rows if r.get("date", "") >= cutoff]

    freq = collections.Counter()
    blocked = collections.Counter()
    examples: dict[str, list[tuple[int, str, str]]] = collections.defaultdict(list)

    for r in rows:
        tags = r.get("gap_tags") or (r.get("evaluation") or {}).get("gap_tags") or []
        if not tags:
            continue
        comps = r.get("components") or (r.get("evaluation") or {}).get("components") or {}
        penalty = abs(comps.get("required_gaps", 0) or 0)
        score = r.get("score") or 0
        # What the posting would have scored without its gaps. A gap on a role
        # that was otherwise strong is the expensive kind.
        potential = score + penalty
        per_tag = penalty / len(tags) if tags else 0

        for t in tags:
            freq[t] += 1
            blocked[t] += per_tag * (potential / 100)
            examples[t].append((potential, r.get("company", ""), r.get("title", "")))

    return {
        "n_rows": len(rows),
        "freq": freq,
        "blocked": blocked,
        "examples": {t: sorted(v, reverse=True)[:3] for t, v in examples.items()},
    }


def company_stats(rows: list[dict], top: int = 15) -> list[tuple]:
    by_co = collections.defaultdict(list)
    for r in rows:
        if r.get("company"):
            by_co[r["company"]].append(r.get("score") or 0)
    out = [(co, len(s), round(statistics.mean(s), 1), max(s))
           for co, s in by_co.items()]
    out.sort(key=lambda x: (-x[3], -x[2]))
    return out[:top]


def _console(res: dict, rows: list[dict]) -> None:
    print(f"\n{res['n_rows']} scored postings in the log\n")
    if not res["freq"]:
        print("No tagged gaps yet. Let the agent run for a few weeks.")
        return

    print(f"{'Skill':<38}{'Required in':>12}{'Blocking cost':>15}")
    print("-" * 65)
    for tag, cost in res["blocked"].most_common(15):
        label = TAG_LABEL.get(tag, tag)
        print(f"{label:<38}{res['freq'][tag]:>9} jobs{cost:>15.1f}")

    print("\nHighest-value roles blocked by the top gap:")
    top_tag = res["blocked"].most_common(1)[0][0]
    for pot, co, title in res["examples"].get(top_tag, []):
        print(f"  {pot:>3} pts  {title[:48]:<48} {co}")

    print("\nCompanies whose postings score best:")
    print(f"{'Company':<32}{'Seen':>6}{'Mean':>8}{'Best':>7}")
    print("-" * 53)
    for co, n, mean, best in company_stats(rows):
        print(f"{co[:31]:<32}{n:>6}{mean:>8}{best:>7}")
    print()


def _html(res: dict, rows: list[dict], path: str = "upskill.html") -> None:
    def esc(s):
        return html.escape(str(s or ""))

    bars = ""
    if res["blocked"]:
        top = res["blocked"].most_common(12)
        peak = max(c for _, c in top) or 1
        for tag, cost in top:
            w = int(100 * cost / peak)
            bars += (
                f"<tr><td style='padding:4px 12px 4px 0;white-space:nowrap'>"
                f"{esc(TAG_LABEL.get(tag, tag))}</td>"
                f"<td style='width:60%'><div style='background:#cf222e;height:14px;"
                f"width:{w}%;border-radius:3px'></div></td>"
                f"<td style='padding-left:10px;color:#57606a;white-space:nowrap'>"
                f"{res['freq'][tag]} jobs</td></tr>"
            )

    co_rows = "".join(
        f"<tr><td>{esc(co)}</td><td align='right'>{n}</td>"
        f"<td align='right'>{mean}</td><td align='right'><b>{best}</b></td></tr>"
        for co, n, mean, best in company_stats(rows)
    )

    doc = f"""<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
      max-width:820px;margin:0 auto;padding:24px;color:#1f2328">
  <h2>Skill gap ledger &mdash; {date.today().isoformat()}</h2>
  <p style="color:#57606a">{res['n_rows']} scored postings.
  Bars are weighted by how well each blocked posting would otherwise have
  scored, so a gap on a strong role outweighs the same gap on a weak one.</p>
  <table style="width:100%;font-size:14px;border-collapse:collapse">{bars}</table>
  <h3 style="margin-top:32px">Companies by best score seen</h3>
  <table style="width:100%;font-size:14px;border-collapse:collapse">
    <tr style="text-align:left;color:#57606a;font-size:12px">
      <th>Company</th><th align="right">Postings</th>
      <th align="right">Mean</th><th align="right">Best</th></tr>
    {co_rows}
  </table>
  <p style="color:#8c959f;font-size:12px;margin-top:28px">
    Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}.</p>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Skill gap ledger from data/jobs.jsonl")
    ap.add_argument("--days", type=int, default=None,
                    help="only consider postings from the last N days")
    ap.add_argument("--html", action="store_true", help="also write upskill.html")
    args = ap.parse_args()

    rows = state.read_log()
    if not rows:
        print("data/jobs.jsonl is empty. Nothing to analyse yet.")
        return

    res = analyse(rows, args.days)
    _console(res, rows)
    if args.html:
        _html(res, rows)


if __name__ == "__main__":
    main()
