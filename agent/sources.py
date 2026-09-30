"""Fetch job postings from public ATS endpoints.

Every fetcher returns a list of dicts with a common shape:
    {id, company, title, location, url, description, posted_at, source}

Fetchers never raise. A dead board should not kill the whole run, so failures
are logged and return an empty list.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

TIMEOUT = 25
UA = "job-agent/2.0 (personal job search)"
HEADERS = {"User-Agent": UA}


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|li|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get(url: str, **kw) -> Any:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------- #
# Greenhouse
# --------------------------------------------------------------------------- #

def greenhouse(board: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    try:
        data = _get(url)
    except Exception as e:
        log.warning("greenhouse/%s failed: %s", board, e)
        return []

    out = []
    for j in data.get("jobs", []):
        out.append({
            "id": f"gh:{board}:{j['id']}",
            "company": board,
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": _strip_html(j.get("content")),
            "posted_at": j.get("updated_at", ""),
            "source": "greenhouse",
        })
    return out


# --------------------------------------------------------------------------- #
# Lever
# --------------------------------------------------------------------------- #

def lever(board: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    try:
        data = _get(url)
    except Exception as e:
        log.warning("lever/%s failed: %s", board, e)
        return []

    out = []
    for j in data:
        body = j.get("descriptionPlain") or _strip_html(j.get("description"))
        for sect in j.get("lists", []):
            body += "\n\n" + sect.get("text", "") + "\n" + _strip_html(sect.get("content"))
        out.append({
            "id": f"lv:{board}:{j.get('id')}",
            "company": board,
            "title": j.get("text", ""),
            "location": (j.get("categories") or {}).get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": body.strip(),
            "posted_at": str(j.get("createdAt", "")),
            "source": "lever",
        })
    return out


# --------------------------------------------------------------------------- #
# Ashby
# --------------------------------------------------------------------------- #

def ashby(board: str) -> list[dict]:
    url = (f"https://api.ashbyhq.com/posting-api/job-board/{board}"
           f"?includeCompensation=true")
    try:
        data = _get(url)
    except Exception as e:
        log.warning("ashby/%s failed: %s", board, e)
        return []

    out = []
    for j in data.get("jobs", []):
        comp = j.get("compensation") or {}
        out.append({
            "id": f"ab:{board}:{j.get('id')}",
            "company": data.get("name") or board,
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("jobUrl", ""),
            "description": j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml")),
            "posted_at": j.get("publishedAt", ""),
            "source": "ashby",
            "salary_note": _ashby_salary(comp),
        })
    return out


def _ashby_salary(comp: dict) -> str:
    """Ashby is one of the few boards that returns structured compensation."""
    try:
        for tier in comp.get("compensationTierSummary", []) or []:
            if isinstance(tier, str) and "$" in tier:
                return tier
        summary = comp.get("summaryComponents") or []
        for c in summary:
            if c.get("compensationType") == "Salary":
                lo, hi = c.get("minValue"), c.get("maxValue")
                if lo and hi:
                    return f"${int(lo):,}–${int(hi):,}"
    except Exception:
        pass
    return ""


# --------------------------------------------------------------------------- #
# SmartRecruiters
# --------------------------------------------------------------------------- #

def smartrecruiters(company: str, limit: int = 100) -> list[dict]:
    base = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    try:
        data = _get(base, params={"limit": limit})
    except Exception as e:
        log.warning("smartrecruiters/%s failed: %s", company, e)
        return []

    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        out.append({
            "id": f"sr:{company}:{j.get('id')}",
            "company": company,
            "title": j.get("name", ""),
            "location": ", ".join(filter(None, [loc.get("city"), loc.get("region"),
                                                loc.get("country")])),
            "url": f"https://jobs.smartrecruiters.com/{company}/{j.get('id')}",
            "description": "",
            "posted_at": j.get("releasedDate", ""),
            "source": "smartrecruiters",
            "_detail": f"{base}/{j.get('id')}",
        })
    return out


# --------------------------------------------------------------------------- #
# Workday
#
# Every Workday tenant exposes an undocumented but stable POST endpoint used by
# its own careers UI. It is the only practical way to reach big pharma, and the
# most brittle source here: tenants rename sites and change wdN hosts without
# notice. Re-run `python -m agent.verify` every couple of months.
#
# Blind paging pulls the tenant's entire req list (thousands at Merck), so this
# searches by keyword instead.
# --------------------------------------------------------------------------- #

def workday(cfg: dict, search_terms: list[str] | None = None,
            per_term: int = 40) -> list[dict]:
    name, host = cfg["name"], cfg["host"].rstrip("/")
    tenant, site = cfg["tenant"], cfg["site"]
    url = f"{host}/wday/cxs/{tenant}/{site}/jobs"
    terms = search_terms or [""]

    seen: dict[str, dict] = {}
    for term in terms:
        offset = 0
        try:
            while offset < per_term:
                payload = {"appliedFacets": {}, "limit": 20, "offset": offset,
                           "searchText": term}
                r = requests.post(url, json=payload, timeout=TIMEOUT,
                                  headers={**HEADERS, "Accept": "application/json",
                                           "Content-Type": "application/json"})
                r.raise_for_status()
                posts = r.json().get("jobPostings", [])
                if not posts:
                    break
                for j in posts:
                    path = j.get("externalPath", "")
                    jid = f"wd:{tenant}:{path}"
                    if jid in seen:
                        continue
                    seen[jid] = {
                        "id": jid,
                        "company": name,
                        "title": j.get("title", ""),
                        "location": j.get("locationsText", ""),
                        "url": f"{host}/{site}{path}",
                        "description": "",
                        "posted_at": j.get("postedOn", ""),
                        "source": "workday",
                        "_detail": f"{host}/wday/cxs/{tenant}/{site}{path}",
                    }
                offset += 20
                time.sleep(0.4)
        except Exception as e:
            log.warning("workday/%s term=%r failed: %s", name, term, e)

    return list(seen.values())


# --------------------------------------------------------------------------- #
# Adzuna — broad fallback, free tier
# --------------------------------------------------------------------------- #

def adzuna(app_id: str, app_key: str, country: str, query: str,
           pages: int = 2, retries: int = 3) -> list[dict]:
    """Adzuna's free tier returns 503 under load often enough that a single
    attempt loses most queries. Retries with backoff on 5xx and 429 only —
    a 401 means the key is wrong and no amount of retrying will fix it."""
    out = []
    for page in range(1, pages + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        data = None
        for attempt in range(retries):
            try:
                data = _get(url, params={
                    "app_id": app_id, "app_key": app_key,
                    "results_per_page": 50, "what": query,
                    "max_days_old": 3, "content-type": "application/json",
                })
                break
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    wait = 2 ** attempt
                    log.debug("adzuna '%s' p%d got %d, retrying in %ds",
                              query, page, code, wait)
                    time.sleep(wait)
                    continue
                log.warning("adzuna '%s' p%d failed: %s", query, page, e)
                break
            except Exception as e:
                log.warning("adzuna '%s' p%d failed: %s", query, page, e)
                break
        if data is None:
            break
        for j in data.get("results", []):
            out.append({
                "id": f"az:{j.get('id')}",
                "company": (j.get("company") or {}).get("display_name", ""),
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("display_name", ""),
                "url": j.get("redirect_url", ""),
                "description": _strip_html(j.get("description")),
                "posted_at": j.get("created", ""),
                "source": "adzuna",
                "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"),
            })
        time.sleep(0.3)
    return out


# --------------------------------------------------------------------------- #
# USAJOBS — federal. NIH, FDA, CDC, VA.
# --------------------------------------------------------------------------- #

def usajobs(email: str, api_key: str, query: str) -> list[dict]:
    url = "https://data.usajobs.gov/api/search"
    headers = {"Host": "data.usajobs.gov", "User-Agent": email,
               "Authorization-Key": api_key}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, params={
            "Keyword": query, "ResultsPerPage": 50, "DatePosted": 3,
        })
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("usajobs '%s' failed: %s", query, e)
        return []

    out = []
    for item in data.get("SearchResult", {}).get("SearchResultItems", []):
        d = item.get("MatchedObjectDescriptor", {})
        ui = d.get("UserArea", {}).get("Details", {})
        body = "\n\n".join(filter(None, [
            d.get("QualificationSummary", ""),
            ui.get("JobSummary", ""),
            ui.get("MajorDuties") and "\n".join(ui["MajorDuties"]) or "",
        ]))
        locs = [x.get("LocationName", "") for x in d.get("PositionLocation", [])]
        pay = (d.get("PositionRemuneration") or [{}])[0]
        out.append({
            "id": f"us:{d.get('PositionID')}",
            "company": d.get("OrganizationName", ""),
            "title": d.get("PositionTitle", ""),
            "location": "; ".join(locs[:3]),
            "url": d.get("PositionURI", ""),
            "description": _strip_html(body),
            "posted_at": d.get("PublicationStartDate", ""),
            "source": "usajobs",
            "salary_min": pay.get("MinimumRange"),
            "salary_max": pay.get("MaximumRange"),
        })
    return out


# --------------------------------------------------------------------------- #
# Lazy body fetch for sources whose list endpoint omits the description
# --------------------------------------------------------------------------- #

def enrich(job: dict) -> dict:
    """Fill in `description` for postings that need a second request."""
    detail = job.pop("_detail", None)
    if not detail or job.get("description"):
        return job
    try:
        data = _get(detail)
    except Exception as e:
        log.debug("enrich failed for %s: %s", job["id"], e)
        return job

    if job["source"] == "workday":
        info = data.get("jobPostingInfo", {})
        job["description"] = _strip_html(info.get("jobDescription"))
        if info.get("startDate"):
            job["posted_at"] = info["startDate"]
    elif job["source"] == "smartrecruiters":
        ad = data.get("jobAd", {}).get("sections", {})
        parts = [ad.get(k, {}).get("text", "") for k in
                 ("companyDescription", "jobDescription", "qualifications",
                  "additionalInformation")]
        job["description"] = _strip_html("\n\n".join(filter(None, parts)))
    return job
