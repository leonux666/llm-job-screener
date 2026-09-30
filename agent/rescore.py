"""Replay logged postings through the current scoring prompt.

    python -m agent.rescore --last 20 --dry-run
    python -m agent.rescore --last 20

Editing a scoring prompt without this is guesswork. New postings arrive a
handful at a time, so a rubric change would take a week to produce enough
evidence to judge, and by then the pool has changed too. Rescoring holds the
postings constant so the only thing that moved is the prompt.

Output is a side-by-side of old and new scores. Nothing is written to
jobs.jsonl — this is a measurement tool, and polluting the log with replayed
scores would corrupt the very dataset the tool exists to protect.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import yaml

from agent import score, state

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=15,
                    help="rescore the N most recently logged postings")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be rescored, spend nothing")
    args = ap.parse_args()

    rows = [r for r in state.read_log() if r.get("description")]
    if not rows:
        print("No logged postings with descriptions yet.\n"
              "Descriptions are only stored from v2 onward, so run the agent "
              "once first.")
        return 0

    batch = rows[-args.last:]
    print(f"{len(batch)} postings to replay "
          f"({batch[0]['date']} to {batch[-1]['date']})\n")

    if args.dry_run:
        for r in batch:
            print(f"  {r.get('score'):>3}  {r['title'][:52]:<52} {r['company']}")
        est = len(batch) * 0.012
        print(f"\nDry run. Rescoring these would cost roughly ${est:.2f}.")
        return 0

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set")
        return 1

    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open("profile.md", encoding="utf-8") as f:
        profile = f.read()

    client = score._client(api_key)
    model = cfg["models"]["deep"]

    print(f"{'old':>4}{'new':>6}{'Δ':>6}  {'title':<46} company")
    print("-" * 96)

    moved = []
    for r in batch:
        job = {"id": r["id"], "title": r["title"], "company": r["company"],
               "location": r.get("location", ""),
               "title_tier": r.get("title_tier", "ambiguous"),
               "description": r["description"]}
        verdict = score.deep(client, model, profile, job)
        if not verdict:
            print(f"{r.get('score'):>4}{'ERR':>6}{'':>6}  {r['title'][:46]:<46} {r['company']}")
            continue
        old, new = r.get("score") or 0, verdict.get("score", 0)
        delta = new - old
        arrow = "+" if delta > 0 else ""
        print(f"{old:>4}{new:>6}{arrow + str(delta):>6}  "
              f"{r['title'][:46]:<46} {r['company']}")
        moved.append(delta)

    if moved:
        up = sum(1 for d in moved if d > 0)
        down = sum(1 for d in moved if d < 0)
        print(f"\n{len(moved)} rescored — {up} up, {down} down, "
              f"{len(moved) - up - down} unchanged. "
              f"Mean shift {sum(moved) / len(moved):+.1f}.")
        print("\nRead the direction, not the magnitude. Scores rising across "
              "the board means the rubric got looser, not that the postings "
              "got better.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
