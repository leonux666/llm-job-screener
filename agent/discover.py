"""Find out which ATS a company actually uses.

Guessing a Greenhouse token fails about half the time not because the token is
misspelled, but because the company moved to a different platform. This tries a
slug against every supported ATS and tells you which one answers.

    python -m agent.discover insitro
    python -m agent.discover insitro benchling tempus grail

Then copy the winning line into the right section of config.yaml.
"""

from __future__ import annotations

import sys

# Windows consoles default to the system codepage (GBK on Chinese Windows).
# Job titles routinely contain accented characters and en dashes, which would
# raise UnicodeEncodeError on print. Force UTF-8 output where the runtime allows it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys

from agent import sources

PLATFORMS = [
    ("greenhouse", sources.greenhouse),
    ("lever", sources.lever),
    ("ashby", sources.ashby),
    ("smartrecruiters", sources.smartrecruiters),
]

# Companies often register a slug that isn't just the lowercased name.
def variants(slug: str) -> list[str]:
    s = slug.strip().lower()
    out = [s, s.replace(" ", ""), s.replace(" ", "-"), s.replace("-", "")]
    seen, uniq = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def probe(slug: str) -> None:
    print(f"\n=== {slug} ===")
    hits = []
    for name, fn in PLATFORMS:
        for v in variants(slug):
            try:
                got = fn(v)
            except Exception:
                got = []
            if got:
                hits.append((name, v, len(got)))
                print(f"  FOUND  {name:<16} token='{v}'  {len(got)} postings")
                break

    if not hits:
        print("  nothing found. The company is probably on Workday, Taleo, iCIMS,")
        print("  or SuccessFactors. Open their careers page and look at the URL:")
        print("    *.myworkdayjobs.com   -> add under sources.workday")
        print("    taleo / icims / sap   -> no public API; rely on Adzuna instead")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for slug in sys.argv[1:]:
        probe(slug)


if __name__ == "__main__":
    main()
