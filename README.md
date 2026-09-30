# llm-job-screener

A daily job scanner that reads public job boards, throws out the postings you
would never take, scores the rest against a profile you write using Claude, and
emails you a digest.

**It is a market-intelligence tool, not an application tool.** It does not submit
applications: automated submission violates most ATS terms of service and, for
senior or research-level roles, does worse than a targeted application. What it
actually produces is an append-only log in `data/jobs.jsonl` that after a few
months can answer questions a job board cannot:

- which employers hire this profile *continuously*, rather than once
- which requirements keep appearing just out of reach
- how long requisitions actually stay open before closing
- what salary bands look like where disclosure is required

If you want a list of jobs to apply to today, this is the wrong tool. If you are
six to eighteen months out from a search and want to know where to aim, this is
what it is for.

---

## Pipeline

```
 ┌──────────────── SOURCES ────────────────┐
 │ Greenhouse   Lever   Ashby              │  public ATS job-board endpoints
 │ SmartRecruiters   Workday               │  (no key)
 │ Adzuna   USAJOBS                        │  official APIs (free key)
 └────────────────────┬────────────────────┘
                      │  ~1,000-2,000 raw postings
                      ▼
 ┌─────────────────────────────────────────┐
 │ DEDUPE            agent/dedupe.py       │  one requisition arriving from
 │                                         │  four feeds is still one job
 └────────────────────┬────────────────────┘
                      ▼
 ┌─────────────────────────────────────────┐
 │ FILTERS           agent/filters.py      │  free. no API calls.
 │  · title keyword gate  (include/exclude)│
 │  · location tiers      (excluded only)  │
 │  · deal-breaker regex  (veto, not score)│
 └────────────────────┬────────────────────┘
                      │  tens of postings
                      ▼
 ┌─────────────────────────────────────────┐
 │ TRIAGE            Claude Haiku 4.5      │  batched 20 at a time,
 │                   one score per posting │  1,200 chars of each body
 └────────────────────┬────────────────────┘
                      │  top `triage_keep` (default 15)
                      ▼
 ┌─────────────────────────────────────────┐
 │ DEEP SCORING      Claude Sonnet         │  one call per posting,
 │                   structured verdict    │  9,000 chars, additive rubric
 └────────────────────┬────────────────────┘
                      ├──────────────▶ data/jobs.jsonl   (everything scored)
                      ▼
 ┌─────────────────────────────────────────┐
 │ DIGEST            agent/report.py       │  HTML email, score breakdown,
 │                                         │  matches vs. required-but-unmet
 └─────────────────────────────────────────┘
```

Two things about that shape are deliberate:

**The free filters come before the paid ones.** Every posting that survives the
keyword gate costs money, so the gate is the main cost lever, and deal-breakers
*veto* rather than subtract points, because "requires a security clearance" is
not "minus twenty", it is "not a job I can take".

**Everything deep-scored is logged, not just what passed.** The sub-threshold
postings are most of the market intelligence: they are what tells you which
requirement keeps appearing one notch above your reach.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/leonux666/llm-job-screener.git
cd llm-job-screener
pip install -r requirements.txt
```

### 2. Copy the three templates

Nothing runs until you do this. All three live files are gitignored: they
describe *you*, not the project.

```bash
cp .env.example      .env
cp config.example.yaml config.yaml
cp profile.example.md  profile.md
```

### 3. Add your Anthropic API key

Edit `.env` and set `ANTHROPIC_API_KEY`. Get one at
[console.anthropic.com](https://console.anthropic.com). The Adzuna and USAJOBS
keys are optional: leave them blank and those sources are skipped.

On Windows PowerShell, load `.env` into your session with:

```powershell
. .\load-env.ps1
```

The leading dot matters: it runs the script in your current shell rather than a
child process, which is the only way the variables survive past the script.

### 4. Write your profile

`profile.md` is the single most important file. See
[Writing your profile](#writing-your-profile) below.

### 5. Check your sources, then run

```bash
python -m agent.verify    # which board tokens are alive? free, no LLM calls
python -m agent.main      # the real thing
```

Then open `digest.html`.

Expect `verify` to report dead sources on a fresh clone. **Every board token in
`config.example.yaml` is an example, not a verified list**: companies move
between ATS platforms without notice. Delete what fails and add your own with
`python -m agent.discover <company-name>`.

**`sources.workday` ships empty, deliberately.** The Greenhouse, Lever, Ashby and
SmartRecruiters entries are example board tokens on those platforms' public
job-board APIs. Workday is different: the fetcher reads an undocumented endpoint
that a careers page calls to render itself, so a ready-made tenant list would
amount to suggesting those particular employers are fine to poll. That is your
call to make per employer, against their terms (see [Where the postings come
from](#where-the-postings-come-from-and-your-responsibility)). The config block
documents the format and `agent/discover.py` will tell you when a company is on
Workday; adding tenants is left to you.

Keep the `workday: []` empty list if you add none. A bare `workday:` with only
comments under it parses as null rather than an empty list, and the fetch loop
will fail on it.

### 6. Scheduling it (optional)

The workflow in `.github/workflows/daily.yml` ships with **`workflow_dispatch`
only**: manual runs from the Actions tab. The `schedule:` block is commented
out on purpose, so cloning this repository does not start a scanner you did not
ask for.

To run it daily, uncomment the `schedule:` block. **Only do this in a private
repo**, because the workflow commits your scored job history to `data/` (see
[Keep your repo private](#keep-your-repo-private)).

---

## GitHub Actions secrets

Under **Settings → Secrets and variables → Actions → New repository secret**.
Nothing is read from a file in CI; every value arrives as an environment
variable.

| Secret | Required | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | console.anthropic.com → API keys |
| `MAIL_USERNAME` | for email | SMTP username, e.g. your Gmail address |
| `MAIL_PASSWORD` | for email | SMTP password. For Gmail this must be an [App Password](https://support.google.com/accounts/answer/185833), not your account password, and it requires 2FA enabled |
| `MAIL_TO` | for email | where the digest is sent |
| `ADZUNA_APP_ID` | optional | developer.adzuna.com, free tier |
| `ADZUNA_APP_KEY` | optional | as above |
| `USAJOBS_EMAIL` | optional | contact address USAJOBS requires in the User-Agent header (it is **sent to data.usajobs.gov with every request**), so use an address you are willing to disclose |
| `USAJOBS_KEY` | optional | developer.usajobs.gov, free |

The digest step uses [`dawidd6/action-send-mail`](https://github.com/dawidd6/action-send-mail),
pinned to the `@v3` tag. If you would rather not trust a moving tag with your
SMTP password, pin it to a commit SHA instead.

### Keep your repo private

The scheduled workflow commits `data/` back to the repository so that dedup
state and the accumulated log survive between runs. That directory ends up
holding your scored job history, including Claude's written assessments of how
you match each posting, which will name your skills and your gaps.

`data/` is gitignored, so a stray `git add -A` cannot publish it. The workflow
uses `git add -f` to opt that one directory back in, and only in CI. But the
result is the same either way: **the repository you actually run this in should
be private.** If you would rather `data/` never enter git at all, delete the
"Commit state" step: the run becomes stateless and every posting looks new
every day.

---

## Writing your profile

`profile.md` is passed verbatim into both scoring prompts. The code contains no
description of any candidate: every judgement the model makes about fit traces
back to this one file. `profile.example.md` is a section-by-section template;
the headings matter, because the scoring prompt refers to them by name.

Three things determine whether the output is any good:

**Be honest about gaps.** This is the counterintuitive one. A profile that
flatters you produces a scorer that quietly filters you toward roles you will not
get, and you will not notice, because everything it shows you looks like a match.
The `## Known gaps` section is also what makes the skill ledger work: gaps are
tagged from a controlled vocabulary and counted across months, so over time the
tool tells you which missing skills are actually *blocking the roles you want*,
a much shorter list than "skills I don't have".

**State things rather than implying them.** The model is instructed never to
infer: if the posting does not say it, it is not a requirement, and if your
profile does not say it, it is not a constraint. An unstated location preference
does not exist for scoring purposes.

**Sanity-check it for the first week.** Read the `gaps` field on every posting in
the digest and confirm each one really appears in the job description, marked as
required. If the model calls something a gap that you have, or claims a match you
do not, fix `profile.md` immediately: that is the feedback loop.

### Tuning `config.yaml`

| Symptom | Fix |
|---|---|
| Wrong *kinds* of companies scoring highest | Edit `sources:`. This is almost always the real problem. |
| Too many irrelevant results | Tighten `keywords.include`, or raise `report.min_score`. |
| Too few results | Usually dead board tokens, not a strict filter. Run `agent.verify` before loosening anything. |
| Roles you would never take keep appearing | Add a `deal_breakers` pattern. |
| A skill is wrongly called a gap | Fix `profile.md`, not the config. |

**Adding companies is the highest-leverage change available**: every board token
is a whole company's pipeline. Bias the list toward employers whose actual work
overlaps yours; famous names that mostly post engineering roles inflate the fetch
count while contributing nothing scoreable.

### After changing the scoring prompt

```bash
python -m agent.rescore --last 20 --dry-run   # free, shows what would replay
python -m agent.rescore --last 20             # ~$0.25
```

Replays logged postings through the current prompt and prints old vs. new side by
side, so the postings stay fixed while only the prompt moves. Read the direction,
not the magnitude: scores rising across the board means the rubric got looser, not
that the postings got better. Nothing is written to `jobs.jsonl` during a rescore.
(See `KNOWN_ISSUES.md` #1: replay is not perfectly like-for-like on long
postings.)

### Monthly

```bash
python -m agent.upskill --html
```

The skill gap ledger, sorted by **blocking cost** rather than frequency: a gap
that costs eight points on a posting that would otherwise have scored 85 matters
far more than the same gap on one that would have scored 40. That column is the
curriculum.

---

## Cost

Roughly **$0.20–$0.30 per run**, so **$6–9/month** on a daily schedule. GitHub
Actions is free at this volume (~90 of the 2,000 free minutes per month), and
Adzuna and USAJOBS are free tiers.

The estimate below assumes the deep stage runs at its `triage_keep: 15` cap (the
usual case once a decent source list is in place), a ~1,000-token profile, and
list prices of $1/$5 per Mtok for Haiku 4.5 and $2/$10 for Sonnet:

| Stage | Calls | Input | Output | Cost |
|---|---|---|---|---|
| Triage (Haiku 4.5) | 1-3 batches of 20 | ~8-24k tok | ~0.2k tok | ~$0.01-0.03 |
| Deep (Sonnet) | 15 | ~71k tok | ~9k tok | ~$0.23 |
| | | | | **~$0.25** |

Note the shape of a *steady-state* day: only postings that are new since the last
run are ever scored, so after the first week a run often has far fewer than 15
candidates and costs correspondingly less. The first run is the expensive one.

Your number will differ, mostly with how long your profile is: it is resent on
every single call. The levers, in order of effect:

- **`report.triage_keep`**: directly multiplies the Sonnet cost, which is ~90%
  of the bill. Halving it roughly halves your spend.
- **Profile length**: resent on all 15 deep calls plus every triage batch.
- **`keywords.include`**: a looser gate means more triage batches, though
  triage is the cheap half.

One thing this does *not* do yet: the system prompt and profile are
byte-identical across all 15 deep calls in a run, and nothing sets
`cache_control`, so that prefix is paid at full rate 15 times. Prompt caching
would likely take a meaningful bite out of the Sonnet line. See
`KNOWN_ISSUES.md`.

---

## Where the postings come from, and your responsibility

Three different kinds of endpoint, which matters both for reliability and for
terms of service:

| Source | Kind | Key | Notes |
|---|---|---|---|
| **Adzuna** | Official documented API | free, required | Registered developer API, [developer.adzuna.com](https://developer.adzuna.com). Free tier 250 calls/day |
| **USAJOBS** | Official documented API (US government) | free, required | [developer.usajobs.gov](https://developer.usajobs.gov). Requires a contact email in the User-Agent |
| **Greenhouse** | Public job-board API | none | `boards-api.greenhouse.io`, the endpoint that serves a company's own public careers page |
| **Lever** | Public job-board API | none | `api.lever.co/v0/postings/{board}` |
| **Ashby** | Public job-board API | none | `api.ashbyhq.com/posting-api/job-board/{board}`. One of the few that returns structured salary data |
| **SmartRecruiters** | Public job-board API | none | `api.smartrecruiters.com/v1/companies/{c}/postings` |
| **Workday** | **Undocumented internal endpoint** | none | The `wday/cxs/...` JSON endpoint a Workday careers page calls to render itself. Not a published API, no stability guarantee, and the most brittle source here: tenants rename sites and move `wdN` hosts without notice. Re-run `agent.verify` every couple of months |

Everything fetched is a publicly visible job posting: no authentication, no
scraping behind a login, no CAPTCHA circumvention. Requests are sequential with
deliberate sleeps, and each board is hit once per day.

**You are responsible for complying with the terms of service of every site you
point this at.** Those terms differ per platform and per company, they change,
and some prohibit automated access regardless of how gentle it is. The Workday
row above deserves particular attention: an undocumented endpoint carries no
usage grant, and reading it may be outside a given tenant's terms. Nothing in
this repository constitutes permission to access any particular employer's
systems, and the MIT licence disclaims warranty and liability: review the
sources you enable, and remove any you are not comfortable with.

Two lines the tool does not cross by design: **it never submits an application**,
and **it never sends a posting's instructions to the model as instructions**:
job descriptions are arbitrary internet text, so bodies are delimited and
explicitly marked as untrusted data (`agent/score.py`, `UNTRUSTED_NOTE`).

---

## Layout

```
config.example.yaml       sources, keyword gate, deal-breakers, title/location tiers
profile.example.md        candidate profile template, the file that drives scoring
.env.example              API keys
load-env.ps1              loads .env into a PowerShell session
agent/sources.py          one fetcher per platform. never raises; a dead board returns []
agent/dedupe.py           cross-source dedup: suppresses low-priority copies only
agent/filters.py          keyword gate, location tiers, deal-breaker veto, title tiering
agent/score.py            Haiku triage → Sonnet deep evaluation. all prompts live here
agent/report.py           HTML digest
agent/state.py            seen-ids, requisition lifecycle, append-only log
agent/upskill.py          gap ledger: which missing skills block the best roles
agent/rescore.py          replay logged postings through a changed prompt
agent/verify.py           board token health check
agent/discover.py         find which ATS a company actually uses
agent/main.py             orchestration
.github/workflows/        manual-dispatch scan; daily schedule commented out
tests/test_dedupe.py      dedup cases, each drawn from a real observed collision
```

Read `KNOWN_ISSUES.md` before filing a bug: five are already documented,
including one real one that quietly degrades the Workday sources.

## Licence

MIT, see [LICENSE](LICENSE).
