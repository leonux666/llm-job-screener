"""Tests for cross-source deduplication.

Every case here is drawn from a real pattern observed in data/jobs.jsonl on
2026-08-14, not invented. The comments name the posting each case came from so
that a future reader can go back to the evidence.
"""

from agent.dedupe import (
    dedupe_key,
    find_duplicate_ids,
    normalize_company,
    normalize_title,
)


def job(jid, source, company, title, location="Somewhere"):
    return {"id": jid, "source": source, "company": company,
            "title": title, "location": location}


# --- normalization ----------------------------------------------------------

def test_company_case_and_suffix_folded():
    # Greenhouse stores the board slug "freenome"; Adzuna stores "Freenome".
    assert normalize_company("Freenome") == normalize_company("freenome")
    assert normalize_company("Nurix Therapeutics") == "nurix"
    assert normalize_company("BioMarin Pharmaceutical Inc.") == "biomarin"


def test_distinct_companies_stay_distinct():
    # Abbott is diagnostics/devices; AbbVie is the 2013 pharma spin-off. They
    # are different employers and must never collapse together.
    assert normalize_company("Abbott") != normalize_company("AbbVie")


def test_title_location_suffix_stripped():
    # Adzuna appends the location after " - "; Greenhouse does not.
    assert normalize_title("Computational Biologist - Remote") == \
           normalize_title("Computational Biologist")


def test_seniority_words_preserved():
    # Two distinct requisitions at Freenome. Merging them would hide one.
    assert normalize_title("Staff Computational Biologist") != \
           normalize_title("Computational Biologist")


def test_punctuation_becomes_space_not_nothing():
    # "Scientist I/II" must not collapse into "scientistiii", which would
    # collide with a genuine "Scientist III" posting.
    assert normalize_title("Scientist I/II") == "scientist i ii"
    assert normalize_title("Scientist I/II") != normalize_title("Scientist III")


# --- suppression policy -----------------------------------------------------

def test_adzuna_copy_yields_to_full_body_source():
    # The 2026-08-10 failure: 14 Adzuna copies of one Freenome posting took
    # 14 of the 15 triage slots.
    jobs = [
        job("gh:freenome:1", "greenhouse", "freenome", "Computational Biologist"),
        job("az:1", "adzuna", "Freenome", "Computational Biologist - Remote"),
        job("az:2", "adzuna", "Freenome", "Computational Biologist - Remote"),
    ]
    suppress, _ = find_duplicate_ids(jobs)
    assert suppress == {"az:1", "az:2"}


def test_full_body_duplicates_are_never_suppressed():
    # Three "Scientist I" reqs at AbbVie are three real openings at three
    # sites. Location is not in the key, so the rule must not merge them.
    jobs = [
        job("sr:abbvie:1", "smartrecruiters", "AbbVie", "Scientist I", "Worcester"),
        job("sr:abbvie:2", "smartrecruiters", "AbbVie", "Scientist I", "Irvine"),
        job("sr:abbvie:3", "smartrecruiters", "AbbVie", "Scientist I", "Chicago"),
    ]
    suppress, _ = find_duplicate_ids(jobs)
    assert suppress == set()


def test_adzuna_internal_duplicates_keep_one():
    # Adzuna assigns a separate id per upstream feed, so the same posting
    # arrives several times even when no other source carries it.
    jobs = [
        job("az:1", "adzuna", "Tempus AI", "Bioinformatics Scientist"),
        job("az:2", "adzuna", "Tempus AI", "Bioinformatics Scientist"),
        job("az:3", "adzuna", "Tempus AI", "Bioinformatics Scientist"),
    ]
    suppress, _ = find_duplicate_ids(jobs)
    assert len(suppress) == 2  # exactly one survivor


def test_unique_adzuna_posting_untouched():
    # Adzuna's whole purpose is long-tail companies absent from the source
    # list. Suppressing those would remove its only value.
    jobs = [
        job("az:1", "adzuna", "Valius Sciences", "Computational Biologist"),
        job("gh:freenome:1", "greenhouse", "freenome", "Computational Biologist"),
    ]
    suppress, _ = find_duplicate_ids(jobs)
    assert suppress == set()


def test_aliases_fold_two_spellings():
    aliases = {"dana farber": "dana farber cancer institute"}
    jobs = [
        job("gh:dfci:1", "greenhouse", "Dana-Farber Cancer Institute", "Postdoc"),
        job("az:1", "adzuna", "Dana-Farber", "Postdoc"),
    ]
    assert find_duplicate_ids(jobs)[0] == set()          # without the table
    assert find_duplicate_ids(jobs, aliases)[0] == {"az:1"}   # with it


def test_reasons_distinguish_cross_source_from_within_source():
    jobs = [
        job("gh:x:1", "greenhouse", "X", "Scientist"),
        job("az:1", "adzuna", "X", "Scientist"),
        job("az:2", "adzuna", "Y", "Analyst"),
        job("az:3", "adzuna", "Y", "Analyst"),
    ]
    _, reasons = find_duplicate_ids(jobs)
    assert sum(reasons.values()) == 2
    assert any("within" in r for r in reasons)
    assert any("copy" in r and "within" not in r for r in reasons)


def test_dedupe_key_is_two_parts_only():
    # Location deliberately excluded: sources disagree on how they spell it,
    # and including it splits groups that should merge.
    a = job("1", "adzuna", "Acme", "Scientist", "Boston, MA")
    b = job("2", "adzuna", "Acme", "Scientist", "Boston")
    assert dedupe_key(a) == dedupe_key(b)