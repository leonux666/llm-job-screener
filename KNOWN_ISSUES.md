# Known issues

Open bugs and rough edges, with file and line references. None of these are
fixed; they are documented so you know what you are inheriting.

Line numbers refer to this repository at the initial release commit.

---

## 1. Logged descriptions are truncated at 6000 characters, which silently makes `rescore` unfaithful

There are two different truncation limits, and they disagree:

| Where | Limit | What it affects |
|---|---|---|
| `agent/score.py:274` | 1200 chars | what Haiku sees during triage |
| `agent/score.py:304` | 9000 chars | what Sonnet sees during **live** deep scoring |
| `agent/state.py:27` (`DESC_CAP`), applied at `agent/state.py:145` | 6000 chars | what is **stored** in `data/jobs.jsonl` |

Two consequences, and the second is the one that matters:

**Qualifications sections get cut.** Job descriptions routinely put company
boilerplate and benefits first and the required-qualifications list last, so a
6000-character cut lands squarely in the part the rubric depends on. A gap the
posting listed as required can be missing from the stored text entirely.

**`python -m agent.rescore` is not a like-for-like comparison.** Live scoring
reads up to 9000 characters; a replay reads at most the 6000 that were stored.
So a posting can score differently on replay because the *input* shrank, not
because the prompt changed, which defeats the purpose of the tool, whose whole
job is to hold the postings constant while only the prompt moves. Long postings
are affected; short ones are not, so the effect is uneven across the batch and
easy to misread as prompt sensitivity.

`DESC_CAP` exists to bound file growth (the comment estimates ~10 MB/year). A
fix needs to either raise the cap to at least the scoring limit, or store the
qualifications-bearing tail rather than the head.

## 2. `title_tier()` matches substrings, so some multi-word below-target titles are fragile

`agent/filters.py:56` compares config patterns as plain lowercased substrings.
Below-target patterns are checked first, which is what makes `Sr. Associate
Scientist` correctly read as below target rather than matching `scientist`.

That ordering trick does not generalise. `associate computational biologist` is
listed at `config.example.yaml:114` and works only because the exact phrase
appears in the title; a posting titled `Computational Biologist, Associate` or
`Associate Scientist, Computational Biology` slips through to `at_or_above` even
though it is the same tier of role. Word-boundary or regex matching, with
patterns able to express "associate … biologist" independent of word order,
would fix the class of problem rather than the one string.

## 3. `ModernaTX` and `Moderna` are treated as two companies

`agent/dedupe.py:48` `normalize_company()` strips punctuation and a list of
corporate suffixes (`inc`, `llc`, `pharmaceuticals`, `therapeutics`, …), but
cannot know that one employer trades under two names. Verified:

```
'ModernaTX'   vs 'Moderna'          -> 'modernatx' vs 'moderna'    match=False
'Moderna Inc' vs 'ModernaTX, Inc.'  -> 'moderna'   vs 'modernatx'  match=False
```

Some feeds report the employer as `ModernaTX` and others as `Moderna`, so the
same requisition arriving from two sources is never grouped and never
deduplicated. Every such pair costs a triage slot. `TX` is not in the suffix
list, and should not be: stripping two-letter tails would collide unrelated
employers.

Most of the fix already exists. `normalize_company()`, `dedupe_key()`
(`agent/dedupe.py:70`) and `find_duplicate_ids()` (`agent/dedupe.py:77`) all
accept an optional `aliases: dict[str, str]` and apply it after suffix
stripping. What is missing is a source for it: `agent/main.py:98` calls
`find_duplicate_ids()` with one argument, and there is no `company_aliases:` key
in the config. A `company_aliases: {modernatx: moderna}` block read from
`config.yaml` and threaded through that one call site would close it.

## 4. `greenhouse/10xgenomics` returns 404

Listed at `config.example.yaml:223`. Verified against the live endpoint:

```
10xgenomics      HTTP 404  0 postings
freenome         HTTP 200  21 postings
```

The board token is wrong or the company has moved off Greenhouse. `greenhouse()`
at `agent/sources.py:50` catches the error and returns `[]`, so the run stays
healthy and the source silently contributes nothing, which is exactly the
failure mode `python -m agent.verify` exists to surface. Run `python -m
agent.discover 10xgenomics` to find where they actually post.

This is also a standing reminder that **every board token in
`config.example.yaml` is an example, not a verified list.** Expect others to
have died since release.

## 5. `workday_queries` is dead config: Workday is fetched with an empty search term

A genuine bug, not a rough edge, and it quietly degrades the largest source.

- `config.example.yaml:279` defines `workday_queries:` **nested inside the
  `sources:` block**.
- `agent/main.py:24` reads `cfg.get("workday_search_terms")`, a **top-level**
  key, under a different name.

Neither name resolves to the other. `cfg.get("workday_search_terms")` returns
`None`, the `or [""]` fallback takes over, and `sources.workday(wd, wd_terms)`
at `agent/main.py:40` is called with a single empty search term for every tenant.

The effect is exactly what the comment above `workday_queries` warns about: a
Workday tenant holds thousands of requisitions across every function in the
company, and an empty `searchText` returns an arbitrary slice of them,
overwhelmingly sales, manufacturing and commercial roles, capped at `per_term`
(40). The keyword gate then discards nearly all of it. So every Workday tenant
you configure contributes far less than its fetch count in the log suggests,
and since Workday is the only route to most large employers, that is the
difference between a useful source and a decorative one.

Note that `sources.workday` ships empty in `config.example.yaml`, so you will not
see this until you add a tenant of your own.

Fixing it is a decision about which name is canonical, not just a rename: the
key has to move to the top level, or the read has to become
`cfg["sources"].get("workday_queries")`. Whichever way, `agent/verify.py:43`
passes its own hardcoded `["scientist"]` and would want the same source.

---

## Not a bug, but worth knowing

**No prompt caching.** Within one run the system prompt and the candidate
profile are byte-identical across all 15 deep-scoring calls, and the profile
alone is most of the input. Nothing in `agent/score.py` sets `cache_control`, so
that prefix is paid for at full rate 15 times over. See the cost note in the
README.

**The monthly gap ledger never fires in this repository.** The `upskill` job in
`.github/workflows/daily.yml` is gated on `github.event_name == 'schedule'`, and
the `schedule:` trigger ships commented out. Run it locally with
`python -m agent.upskill --html`.
