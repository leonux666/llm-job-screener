"""Check every board token in config.yaml and report which ones work.

    python -m agent.verify

Run this first, and again every couple of months. Board tokens and Workday site
names change without warning, and a silently dead source is worse than no
source: the pipeline keeps looking healthy while the candidate pool quietly
shrinks underneath it.
"""

from __future__ import annotations

import yaml

from agent import sources

OK, DEAD = "  OK", "DEAD"


def main() -> None:
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    src = cfg["sources"]
    dead: list[str] = []

    checks = [
        ("greenhouse", src.get("greenhouse", []), sources.greenhouse),
        ("lever", src.get("lever", []), sources.lever),
        ("ashby", src.get("ashby", []), sources.ashby),
        ("smartrecruiters", src.get("smartrecruiters", []), sources.smartrecruiters),
    ]

    for label, boards, fn in checks:
        print(f"\n--- {label} ---")
        for b in boards:
            got = fn(b)
            print(f"{OK if got else DEAD}  {b:<28} {len(got):>4} postings")
            if not got:
                dead.append(f"{label}:{b}")

    print("\n--- workday ---")
    for wd in src.get("workday", []):
        got = sources.workday(wd, ["scientist"], per_term=20)
        print(f"{OK if got else DEAD}  {wd['name']:<28} {len(got):>4} postings")
        if not got:
            dead.append(f"workday:{wd['name']}")

    if dead:
        print(f"\n{len(dead)} dead source(s) — remove or fix in config.yaml:")
        for d in dead:
            print(f"  - {d}")
    else:
        print("\nAll sources responding.")


if __name__ == "__main__":
    main()
