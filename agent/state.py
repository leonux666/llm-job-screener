"""Persistent state, committed back to the repo by the workflow.

`seen.json`  — every posting id ever fetched, with first_seen / last_seen /
               closed_on. Drives dedup AND requisition lifecycle stats.
`jobs.jsonl` — append-only log of every deep-scored posting, including its
               description. This is the file that accrues value.

Storing the description matters more than it looks: without it, a change to the
scoring rubric cannot be evaluated against past postings, so every prompt edit
means waiting days for fresh data. With it, `python -m agent.rescore` replays
history through the new prompt in one shot.

Every file is opened with an explicit UTF-8 encoding. On a Chinese-locale
Windows install Python defaults to GBK, which throws on the first em dash in a
job description.
"""

from __future__ import annotations

import json
import os
from datetime import date

SEEN = "data/seen.json"
LOG = "data/jobs.jsonl"

DESC_CAP = 6000  # keeps jobs.jsonl to roughly 10 MB/year


def _today() -> str:
    return date.today().isoformat()


# Sources whose list endpoint returns the ENTIRE board in one request. Only
# these can support closure detection: if a posting is absent, it is gone.
#
# Workday, Adzuna and USAJOBS are keyword-SEARCHED and capped (`per_term`), so
# a posting missing from today's results usually just failed to rank into the
# cap — the requisition is still open. Treating that as a closure produced a
# run reporting 265 closures with a median of 1 day open, which is nonsense.
COMPLETE_LISTING_PREFIXES = ("gh:", "lv:", "ab:", "sr:")


def _trackable(job_id: str) -> bool:
    return job_id.startswith(COMPLETE_LISTING_PREFIXES)


def load_seen() -> dict[str, dict]:
    """Returns {id: {first_seen, last_seen, absent_runs, closed_on, backfilled}}."""
    if not os.path.exists(SEEN):
        return {}
    with open(SEEN, encoding="utf-8") as f:
        raw = json.load(f)

    # v1 was {"ids": [...]}. Migrate rather than discard — those ids are the
    # only record of what was already on the market. Their first_seen is
    # unknown, so mark them backfilled and keep them out of duration stats
    # instead of pretending they appeared today.
    ids = raw.get("ids", [])
    if isinstance(ids, list):
        today = _today()
        return {i: {"first_seen": today, "last_seen": today, "absent_runs": 0,
                    "closed_on": None, "backfilled": True} for i in ids}
    return ids


def save_seen(state: dict[str, dict], cap: int = 40000) -> None:
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    if len(state) > cap:
        ordered = sorted(state.items(), key=lambda kv: kv[1].get("last_seen", ""))
        state = dict(ordered[-cap:])
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "ids": state}, f)


def update_lifecycle(state: dict[str, dict], current_ids: set[str],
                     absent_runs_to_close: int = 3) -> list[dict]:
    """Mark postings seen today, close ones that have genuinely vanished.

    Closure is only inferred for sources that return a complete board listing
    (see COMPLETE_LISTING_PREFIXES). For keyword-searched sources, absence
    carries no information and the record is left untouched.

    Returns postings closed on this run. Records whose first_seen was
    backfilled during migration report `days_open: None` — their true start is
    unknown, and a fabricated duration is worse than a missing one.
    """
    today = _today()
    closed = []

    for jid in current_ids:
        rec = state.setdefault(jid, {"first_seen": today, "absent_runs": 0,
                                     "closed_on": None})
        rec["last_seen"] = today
        rec["absent_runs"] = 0

    for jid, rec in state.items():
        if jid in current_ids or rec.get("closed_on") or not _trackable(jid):
            continue
        rec["absent_runs"] = rec.get("absent_runs", 0) + 1
        if rec["absent_runs"] >= absent_runs_to_close:
            rec["closed_on"] = today
            days = (None if rec.get("backfilled")
                    else _days_between(rec.get("first_seen"), today))
            closed.append({"id": jid, "first_seen": rec.get("first_seen"),
                           "closed_on": today, "days_open": days})
    return closed


def _days_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except ValueError:
        return None


def append_log(jobs: list[dict]) -> None:
    """Log every deep-scored posting, whatever it scored."""
    if not jobs:
        return
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    today = _today()
    with open(LOG, "a", encoding="utf-8") as f:
        for j in jobs:
            ev = j.get("evaluation") or {}
            rec = {
                "date": today,
                "id": j["id"],
                "company": j["company"],
                "title": j["title"],
                "location": j.get("location", ""),
                "location_tier": j.get("location_tier"),
                "title_tier": j.get("title_tier"),
                "url": j.get("url", ""),
                "source": j["source"],
                "score": j.get("score"),
                "components": ev.get("components"),
                "insufficient_info": ev.get("insufficient_info"),
                "gap_tags": ev.get("gap_tags", []),
                "evaluation": ev,
                "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"),
                "description": (j.get("description") or "")[:DESC_CAP],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_log() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    rows = []
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows
