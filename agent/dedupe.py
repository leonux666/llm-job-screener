"""Cross-source deduplication.

The same requisition can arrive from several sources. Adzuna is the worst
offender: it assigns a distinct internal id to each upstream feed it ingested
the posting from, so `by_id` never catches those copies. On 2026-08-10 a single
Freenome posting occupied 14 of the 15 triage slots this way.

Policy (deliberately conservative):

  * Group by normalized company + title. Location is NOT part of the key --
    sources disagree on how they spell it, and adding it splits groups that
    should merge.
  * Within a group, suppress copies only from LOW-PRIORITY sources, and only
    down to one survivor. Copies from full-body sources are never touched.

The asymmetry is the point. Three "Scientist I" postings from SmartRecruiters
are three real requisitions at three sites; three from Adzuna are almost
certainly one posting counted three times. Merging the former loses real
openings, so the rule declines to do it.
"""

from __future__ import annotations

import re

# Sources whose list endpoint returns the full posting body and a real
# requisition id. A copy from any of these is authoritative.
FULL_BODY_SOURCES = frozenset({
    "greenhouse", "lever", "ashby", "smartrecruiters", "workday", "usajobs",
})

# Everything not listed above is treated as low priority.
def _is_low_priority(source: str) -> bool:
    return source not in FULL_BODY_SOURCES


_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|company|co|plc|sa|ag|nv|holdings|"
    r"pharmaceuticals|pharmaceutical|pharma|therapeutics|biosciences|"
    r"bioscience|labs|laboratories)\b"
)

# Punctuation becomes a space, never nothing: collapsing "Scientist I/II" to
# "scientistiii" would collide with a genuine "Scientist III" posting.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_company(name: str, aliases: dict[str, str] | None = None) -> str:
    """Fold spelling variants of one employer onto a single key."""
    s = _NON_ALNUM.sub(" ", (name or "").lower())
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = " ".join(s.split())
    if aliases:
        s = aliases.get(s, s)
    return s


def normalize_title(title: str) -> str:
    """Strip trailing qualifiers, keep every seniority word.

    Adzuna appends the location: "Computational Biologist - Remote". The text
    before the first " - " is the title proper. Seniority words are left alone
    because "Staff Computational Biologist" is a different requisition from
    "Computational Biologist", and title_tier is parsed from them downstream.
    """
    head = (title or "").split(" - ")[0]
    return " ".join(_NON_ALNUM.sub(" ", head.lower()).split())


def dedupe_key(job: dict, aliases: dict[str, str] | None = None) -> tuple[str, str]:
    return (
        normalize_company(job.get("company", ""), aliases),
        normalize_title(job.get("title", "")),
    )


def find_duplicate_ids(
    jobs: list[dict],
    aliases: dict[str, str] | None = None,
) -> tuple[set[str], dict[str, int]]:
    """Return (ids to suppress, count of suppressions per reason).

    `jobs` should be every posting seen this run, not just the new ones: a
    yesterday's Greenhouse copy still outranks a today's Adzuna copy.

    The caller must not drop the returned ids from the set it hands to
    lifecycle tracking. An id that vanishes from that set looks like a closed
    requisition, and these postings are open -- they are merely redundant.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for j in jobs:
        groups.setdefault(dedupe_key(j, aliases), []).append(j)

    suppress: set[str] = set()
    reasons: dict[str, int] = {}

    for members in groups.values():
        if len(members) < 2:
            continue

        low = [j for j in members if _is_low_priority(j.get("source", ""))]
        if not low:
            continue  # all authoritative: leave every copy alone

        high_present = len(low) < len(members)
        # Keep one low-priority copy only when no authoritative copy exists.
        losers = low if high_present else low[1:]

        for j in losers:
            jid = j.get("id")
            if not jid:
                continue
            suppress.add(jid)
            reason = (
                f"duplicate of {members[0].get('source')} copy"
                if high_present
                else f"duplicate within {j.get('source')}"
            )
            reasons[reason] = reasons.get(reason, 0) + 1

    return suppress, reasons