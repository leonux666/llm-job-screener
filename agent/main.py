"""Entry point. Run with `python -m agent.main`."""

from __future__ import annotations

import logging
import os
import statistics
import sys

import yaml

from agent import dedupe, filters, report, score, sources, state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent")


def fetch_all(cfg: dict) -> list[dict]:
    src = cfg["sources"]
    wd_terms = cfg.get("workday_search_terms") or [""]
    jobs: list[dict] = []

    simple = [
        ("greenhouse", src.get("greenhouse", []), sources.greenhouse),
        ("lever", src.get("lever", []), sources.lever),
        ("ashby", src.get("ashby", []), sources.ashby),
        ("smartrecruiters", src.get("smartrecruiters", []), sources.smartrecruiters),
    ]
    for label, boards, fn in simple:
        for board in boards:
            got = fn(board)
            log.info("%s/%-*s %3d", label, 34 - len(label), board, len(got))
            jobs += got

    for wd in src.get("workday", []):
        got = sources.workday(wd, wd_terms)
        log.info("workday/%-27s %3d", wd["name"], len(got))
        jobs += got

    az = src.get("adzuna", {})
    if az.get("enabled") and os.getenv("ADZUNA_APP_ID"):
        for q in az.get("queries", []):
            got = sources.adzuna(os.environ["ADZUNA_APP_ID"],
                                 os.environ["ADZUNA_APP_KEY"],
                                 az.get("country", "us"), q)
            log.info("adzuna/%-28s %3d", q[:28], len(got))
            jobs += got

    uj = src.get("usajobs", {})
    if uj.get("enabled") and os.getenv("USAJOBS_KEY"):
        for q in uj.get("queries", []):
            got = sources.usajobs(os.environ["USAJOBS_EMAIL"],
                                  os.environ["USAJOBS_KEY"], q)
            log.info("usajobs/%-27s %3d", q[:27], len(got))
            jobs += got

    return jobs


def _load(path: str, example: str) -> str:
    """Read a user-owned file, or explain which example to copy.

    `config.yaml` and `profile.md` are gitignored on purpose: they are yours, not
    the project's. A first run without them should say so plainly rather than
    raising a bare FileNotFoundError.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log.error("%s not found. Copy the template and edit it:\n"
                  "    cp %s %s", path, example, path)
        raise SystemExit(1)


def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY is not set")
        return 1

    cfg = yaml.safe_load(_load("config.yaml", "config.example.yaml"))
    profile = _load("profile.md", "profile.example.md")

    jobs = fetch_all(cfg)
    by_id = {j["id"]: j for j in jobs}
    log.info("fetched %d postings total", len(by_id))

    seen = state.load_seen()
    # Suppress redundant copies before they compete for triage slots. Compare
    # against every posting seen this run, not just the new ones: yesterday's
    # Greenhouse copy still outranks today's Adzuna copy. by_id itself is left
    # intact -- an id missing from it would read as a closed requisition.
    dup_ids, dup_reasons = dedupe.find_duplicate_ids(list(by_id.values()))
    if dup_ids:
        log.info("%d duplicate copies suppressed", len(dup_ids))
        for reason, n in sorted(dup_reasons.items(), key=lambda kv: -kv[1]):
            log.info("  %3d — %s", n, reason)

    fresh = [j for jid, j in by_id.items()
             if jid not in seen and jid not in dup_ids]
    log.info("%d new since last run", len(fresh))

    # Lifecycle before scoring: closures are free to compute and are worth
    # recording even on a day when nothing new clears the gate.
    lc = cfg.get("lifecycle", {})
    closed = []
    if lc.get("track_closures", True):
        closed = state.update_lifecycle(
            seen, set(by_id), lc.get("absent_runs_to_close", 2))
        if closed:
            days = [c["days_open"] for c in closed if c["days_open"] is not None]
            log.info("%d requisitions closed%s", len(closed),
                     f", median {int(statistics.median(days))} days open" if days else "")

    candidates, drops = filters.apply(fresh, cfg)
    log.info("%d passed the keyword gate", len(candidates))
    for reason, n in sorted(drops.items(), key=lambda kv: -kv[1])[:6]:
        log.info("  dropped %3d — %s", n, reason)

    # Workday and SmartRecruiter list endpoints omit the body. Pay for the
    # second request only after the title gate, then re-run the deal-breaker
    # check now that there is text to check against.
    for j in candidates:
        if not j.get("description"):
            sources.enrich(j)

    rules = cfg.get("deal_breakers", [])
    kept = []
    for j in candidates:
        veto = filters.deal_breaker(j.get("description", ""), rules)
        if veto:
            drops[f"deal-breaker: {veto}"] = drops.get(f"deal-breaker: {veto}", 0) + 1
            continue
        kept.append(j)
    if len(kept) != len(candidates):
        log.info("%d vetoed after body fetch", len(candidates) - len(kept))

    scored = score.run(api_key, cfg, profile, kept)
    if scored:
        log.info("deep scores: %s", ", ".join(str(j["score"]) for j in scored[:12]))

    min_score = cfg["report"]["min_score"]
    passing = [j for j in scored if j["score"] >= min_score]
    top = passing[: cfg["report"]["top_n"]]
    near = ([j for j in scored if j["score"] < min_score][: cfg["report"].get("near_miss", 3)]
            if not top else [])
    log.info("reporting %d%s", len(top),
             f" ({len(near)} near misses)" if near else "")

    days = [c["days_open"] for c in closed if c["days_open"] is not None]
    html = report.render(top, near, {
        "fetched": len(by_id),
        "new": len(fresh),
        "filtered": len(kept),
        "scored": len(scored),
        "drops": drops,
        "closed": len(closed),
        "median_days_open": int(statistics.median(days)) if days else None,
        "footer_note": cfg["report"].get("footer_note", ""),
    })
    with open("digest.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Log every deep-scored posting, not just the ones that passed. The
    # sub-threshold postings are most of the market intelligence: they are what
    # tells you which requirements keep appearing just out of reach.
    state.append_log(scored)
    state.save_seen(seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
