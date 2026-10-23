"""Find companies that are hiring for a role, using public job-board APIs.

Free, no key:   Remotive, RemoteOK, Arbeitnow  (mostly remote / EU jobs)
Free key:       Adzuna (many countries incl. India, UK, US), Jooble (worldwide),
                JSearch on RapidAPI (Google for Jobs: LinkedIn, Indeed, Glassdoor listings)
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobDedo/1.0; personal job search)"}
TIMEOUT = 20

ADZUNA_COUNTRIES = {
    "India": "in", "United States": "us", "United Kingdom": "gb", "Canada": "ca",
    "Australia": "au", "Germany": "de", "France": "fr", "Netherlands": "nl",
    "Singapore": "sg", "New Zealand": "nz", "South Africa": "za", "Italy": "it",
    "Spain": "es", "Poland": "pl", "Brazil": "br", "Mexico": "mx", "Austria": "at",
    "Belgium": "be", "Switzerland": "ch",
}


@dataclass
class JobLead:
    company: str
    job_title: str
    job_url: str
    location: str
    source: str
    description: str = ""


class SourceError(Exception):
    pass


def _clean_html(html: str, limit: int = 2500) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def _matches(query: str, *fields: str) -> bool:
    """Every word of the query must appear in the title/tags."""
    haystack = " ".join(f or "" for f in fields).lower()
    return all(word in haystack for word in query.lower().split())


def _get(url: str, headers: dict | None = None, **kwargs) -> requests.Response:
    try:
        resp = requests.get(url, headers=headers or HEADERS, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        raise SourceError(str(e)) from e


def remotive(query: str, limit: int) -> list[JobLead]:
    data = _get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": limit}).json()
    return [
        JobLead(
            company=j["company_name"],
            job_title=j["title"],
            job_url=j["url"],
            location=j.get("candidate_required_location") or "Remote",
            source="Remotive",
            description=_clean_html(j.get("description", "")),
        )
        for j in data.get("jobs", [])[:limit]
    ]


def remoteok(query: str, limit: int) -> list[JobLead]:
    data = _get("https://remoteok.com/api").json()
    leads = []
    for j in data[1:]:  # first element is a legal notice
        if not _matches(query, j.get("position"), " ".join(j.get("tags") or [])):
            continue
        leads.append(
            JobLead(
                company=j.get("company", ""),
                job_title=j.get("position", ""),
                job_url=j.get("apply_url") or j.get("url", ""),
                location=j.get("location") or "Remote",
                source="RemoteOK",
                description=_clean_html(j.get("description", "")),
            )
        )
        if len(leads) >= limit:
            break
    return leads


def arbeitnow(query: str, limit: int, pages: int = 3) -> list[JobLead]:
    leads = []
    for page in range(1, pages + 1):
        data = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}).json()
        for j in data.get("data", []):
            if not _matches(query, j.get("title"), " ".join(j.get("tags") or [])):
                continue
            leads.append(
                JobLead(
                    company=j.get("company_name", ""),
                    job_title=j.get("title", ""),
                    job_url=j.get("url", ""),
                    location=j.get("location") or ("Remote" if j.get("remote") else ""),
                    source="Arbeitnow",
                    description=_clean_html(j.get("description", "")),
                )
            )
            if len(leads) >= limit:
                return leads
    return leads


def adzuna(query: str, location: str, country: str, app_id: str, app_key: str, limit: int) -> list[JobLead]:
    leads, page = [], 1
    while len(leads) < limit and page <= 5:
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "results_per_page": 50,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location
        data = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params=params).json()
        results = data.get("results", [])
        if not results:
            break
        for j in results:
            leads.append(
                JobLead(
                    company=(j.get("company") or {}).get("display_name", ""),
                    job_title=j.get("title", ""),
                    job_url=j.get("redirect_url", ""),
                    location=(j.get("location") or {}).get("display_name", ""),
                    source="Adzuna",
                    description=_clean_html(j.get("description", "")),
                )
            )
        page += 1
    return leads[:limit]


def jooble(query: str, location: str, api_key: str, limit: int) -> list[JobLead]:
    try:
        resp = requests.post(
            f"https://jooble.org/api/{api_key}",
            json={"keywords": query, "location": location or "", "page": 1},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SourceError(str(e)) from e
    return [
        JobLead(
            company=j.get("company", ""),
            job_title=_clean_html(j.get("title", ""), 200),
            job_url=j.get("link", ""),
            location=j.get("location", ""),
            source="Jooble",
            description=_clean_html(j.get("snippet", "")),
        )
        for j in resp.json().get("jobs", [])[:limit]
    ]


def jsearch(query: str, location: str, api_key: str, limit: int, country: str = "in") -> list[JobLead]:
    """JSearch (RapidAPI): Google for Jobs results, which include LinkedIn, Indeed and Glassdoor postings."""
    pages = max(1, min(3, (limit + 9) // 10))           # 10 jobs per page; every page counts against the free quota
    data = _get(
        "https://jsearch.p.rapidapi.com/search",
        params={"query": f"{query} in {location}" if location else query, "page": 1, "num_pages": pages, "date_posted": "month", "country": country},
        headers={**HEADERS, "X-RapidAPI-Key": api_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
    ).json()
    return [
        JobLead(
            company=j.get("employer_name") or "",
            job_title=j.get("job_title") or "",
            job_url=j.get("job_apply_link") or j.get("job_google_link") or "",
            location="Remote" if j.get("job_is_remote") else ", ".join(x for x in (j.get("job_city"), j.get("job_country")) if x),
            source=f"JSearch · {j.get('job_publisher') or 'web'}",
            description=_clean_html(j.get("job_description") or "", 6000),
        )
        for j in (data.get("data") or [])[:limit]
    ]


def search_all(
    query: str,
    location: str,
    sources: list[str],
    limit_per_source: int,
    keys: dict,
    country: str = "in",
) -> tuple[list[JobLead], dict[str, str]]:
    """Run every selected source. Returns (leads, {source: error message})."""
    runners = {
        "Remotive": lambda: remotive(query, limit_per_source),
        "RemoteOK": lambda: remoteok(query, limit_per_source),
        "Arbeitnow": lambda: arbeitnow(query, limit_per_source),
        "Adzuna": lambda: adzuna(
            query, location, country, keys.get("ADZUNA_APP_ID", ""), keys.get("ADZUNA_APP_KEY", ""), limit_per_source
        ),
        "Jooble": lambda: jooble(query, location, keys.get("JOOBLE_API_KEY", ""), limit_per_source),
        "JSearch": lambda: jsearch(query, location, keys.get("JSEARCH_API_KEY", ""), limit_per_source, country),
    }
    leads, errors = [], {}
    for name in sources:
        try:
            leads.extend(lead for lead in runners[name]() if lead.company.strip())
        except (SourceError, ValueError, KeyError) as e:
            errors[name] = str(e)
    return leads, errors
