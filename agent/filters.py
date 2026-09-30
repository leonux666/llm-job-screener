"""Deterministic filters that run before any LLM call.

Two jobs here:

1. Cost control. Every posting that survives costs money to score, so the gate
   should be tight on obvious rejects and loose on anything genuinely ambiguous
   — an LLM call is cheap, a missed opportunity is not.

2. Deal-breaker vetoes. A posting that fails a deal-breaker is dropped, not
   scored. This is deliberately separate from scoring: a deal-breaker is not
   "minus twenty points", it is "not a job this candidate would take". Keeping
   the two apart stops vetoed roles from crowding the near-miss list and keeps
   the score distribution meaningful.

Location is classified but, with one exception, not filtered: tiers are recorded
for reporting, and only `excluded` drops a posting. Every keyword list lives in
config.yaml under `location_tiers:` — nothing geographic is hardcoded here, and
leaving the block out means locations are recorded and nothing is filtered.
"""

from __future__ import annotations

import re


def _norm(s: str) -> str:
    return " " + (s or "").lower().replace(",", " ").replace("/", " ") + " "


def location_tier(location: str, cfg: dict) -> int:
    """1 = nearby, 2 = would relocate, 3 = remote, 4 = excluded.

    Reporting only, except tier 4: a location matching `excluded` is the one
    geographic reason a posting is dropped, for places the candidate cannot
    accept a role at all. Config keys, all optional and all matched as
    lowercased substrings:

        location_tiers:
          remote:   [remote, work from home]
          nearby:   [<metro areas within commuting distance>]
          excluded: [<countries or regions that are not viable>]

    With no config the function returns 2 for everything, which filters nothing.
    """
    tiers = cfg.get("location_tiers") or {}
    loc = _norm(location)
    if any(k.lower() in loc for k in tiers.get("remote", [])):
        return 3
    if any(k.lower() in loc for k in tiers.get("nearby", [])):
        return 1
    if any(k.lower() in loc for k in tiers.get("excluded", [])):
        return 4
    return 2


def title_tier(title: str, cfg: dict) -> str:
    """at_or_above_target | below_target | ambiguous.

    Below-target patterns are checked FIRST on purpose: "Sr. Associate
    Scientist" contains "scientist" and would otherwise read as on-target,
    which is exactly backwards — it is a BS/MS bench title.
    """
    t = (title or "").lower()
    tiers = cfg.get("title_tiers", {})
    for pat in tiers.get("below_target", []):
        if pat in t:
            return "below_target"
    for pat in tiers.get("at_or_above", []):
        if pat in t:
            return "at_or_above_target"
    return "ambiguous"


def title_gate(title: str, include: list[str], exclude: list[str]) -> bool:
    t = (title or "").lower()
    if any(x in t for x in exclude):
        return False
    return any(x in t for x in include)


def deal_breaker(description: str, rules: list[dict]) -> str | None:
    """Return the reason string for the first matching veto, else None."""
    d = (description or "").lower()
    for rule in rules or []:
        if re.search(rule["pattern"], d, flags=re.I):
            return rule.get("reason", rule["pattern"])
    return None


def apply(jobs: list[dict], cfg: dict) -> tuple[list[dict], dict[str, int]]:
    """Returns (kept, drop_reason_counts)."""
    inc = [k.lower() for k in cfg["keywords"]["include"]]
    exc = [k.lower() for k in cfg["keywords"]["exclude"]]
    rules = cfg.get("deal_breakers", [])

    kept: list[dict] = []
    drops: dict[str, int] = {}

    def _drop(reason: str) -> None:
        drops[reason] = drops.get(reason, 0) + 1

    for j in jobs:
        if not title_gate(j.get("title", ""), inc, exc):
            _drop("title gate")
            continue

        tier = location_tier(j.get("location", ""), cfg)
        if tier == 4:
            _drop("excluded location")
            continue

        # Body may be empty at this stage for Workday/SmartRecruiters; those get
        # re-checked after enrich() in main.py.
        veto = deal_breaker(j.get("description", ""), rules)
        if veto:
            _drop(f"deal-breaker: {veto}")
            continue

        j["location_tier"] = tier
        j["title_tier"] = title_tier(j.get("title", ""), cfg)
        kept.append(j)

    return kept, drops
