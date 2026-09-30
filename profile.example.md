# Candidate profile (EXAMPLE TEMPLATE)

    cp profile.example.md profile.md

`profile.md` is gitignored. It is the only file describing you, and it is passed
verbatim into both scoring prompts, so write it for a reader who knows nothing
about you and cannot ask follow-up questions.

Replace every `[bracketed]` placeholder and delete the guidance notes as you go.
Keep the section headings: the scoring prompt refers to them by name
("the profile's strengths section", "a title the profile lists as below target"),
so renaming or removing a section quietly weakens the rubric.

Two rules worth internalising before you write anything:

1. **Be honest about gaps.** A profile that flatters you is worse than no profile
   at all: it filters you toward roles you will not get, and it does so
   invisibly. The scorer can only be as accurate as this file.
2. **State things, do not imply them.** The model is instructed never to infer.
   If a constraint is not written here, it does not exist for scoring purposes.

---

## Status and timing

- [Current role or status, e.g. "Ph.D. candidate in X, defending Spring 2027",
  "Senior engineer at a mid-size SaaS company", "Between roles since March".]
- [Earliest start date, stated as a date. This is one of the highest-value lines
  in the file: it drives the `start_date_risk` field.]
- [How a credential in progress should be treated. Be specific about when an
  unfinished degree or certification is and is not a gap, because postings state
  this inconsistently. Example: "Will hold the degree by May 2027. A posting
  requiring a completed degree is NOT a gap when its start date is May 2027 or
  later. It IS a gap when the posting names an earlier conferral deadline or a
  fixed cohort start date."]
- [Work authorization, if it affects eligibility. State it plainly: it is
  frequently a hard requirement and sometimes a genuine advantage.]
- [Location, and whether it constrains anything. If you will relocate, say so
  explicitly and say it is not a filter; the scorer applies whatever this file
  states and nothing more.]

## Target roles

[The two or three job families you actually want, and the kinds of employer.
Write titles as they appear in postings, not as you would describe them.]

## Title tiers

The scorer reads this to award `level_fit`. Getting it wrong is expensive in
both directions: too generous and you get flooded, too strict and you never see
the stretch roles.

- **At or above target**: [titles you want, including the seniority variants:
  "X", "Senior X", "X I/II", "Staff X".]
- **Below target** (screens you out as overqualified, or is a step down):
  [titles that look adjacent but are not, plus the experience bands that
  disqualify you, e.g. "anything asking for BS/MS with 2-5 years". Note that
  substring matching applies: listing "Associate X" here is what stops
  "Senior Associate X" from reading as on-target.]

## Core technical strengths

Only list things you have actually done and could be questioned on. The scorer
awards `core_technical` against this section and is told never to credit a skill
the profile does not claim.

- [Skill area]: [specific tools, methods, scale. "R (strong), Python (solid)"
  is more useful than "programming".]
- [Skill area]: [...]
- [Skill area]: [...]

## Known gaps

Do NOT score these as strengths. Flag them ONLY when the posting explicitly
requires them.

This section is what makes `python -m agent.upskill` work: gaps get tagged from
a controlled vocabulary and counted across months, so over time the tool tells
you which missing skills are actually blocking the roles you want, as opposed
to which are merely common.

- [A skill you do not have.] [Optionally note if you have observed it recurring
  in postings you care about.]
- [A skill you do not have.]
- [Certification or environment experience you lack.]

## Deal-breakers

A posting matching any of these is rejected outright, not scored. Keep this list
short and absolute: anything you would merely prefer to avoid belongs in
Preferences, not here.

- [A role type you would decline regardless of how well it matched.]
- [Another.]

Deal-breakers expressed as text patterns rather than judgement calls belong in
`config.yaml` under `deal_breakers:`, where they are matched by regex and cost
nothing. Use this section for the ones that need reading comprehension.

## Preferences

Soft signals. These shift `work_type` and `role_quality` but never veto.

- [What kind of work you want at the centre of the job.]
- [Employer types you prefer, and why.]
- [How to treat disclosed salary. Note that most postings disclose nothing, and
  the rubric already awards a neutral 8 in that case: absence of a salary must
  never count against a posting.]

## Evaluating borderline role types

Optional, and the most useful section in the file once your log has a few months
in it. Use it for a category of posting that keeps appearing and that a title
match alone cannot judge: the roles where you find yourself re-litigating the
same decision every week.

Give the model a test with a threshold rather than a vibe. For example:

> [Category of role] is only in scope if the posting provides evidence for at
> least two of the following. Judge only on text stated in the posting; do not
> infer.
>
> 1. [Criterion, e.g. it names a skill from the Known gaps section above, so
>    taking it would close a gap that recurs in target postings.]
> 2. [Criterion, e.g. location or a stated industry partnership.]
> 3. [Criterion, e.g. the subject area is one your target employers hire from
>    directly, with the out-of-scope areas named explicitly.]
>
> A posting meeting fewer than two is not a fit even when the underlying methods
> overlap with your existing work. Methodological overlap is not career fit.

The "at least two of" construction matters. A single criterion is too easy to
satisfy and a checklist of five is too easy to fail; a threshold forces the model
to weigh the posting instead of pattern-matching one phrase in it.
