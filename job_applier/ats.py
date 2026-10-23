"""Read open jobs straight from company career pages.

Most startups host their careers page on an applicant tracking system (ATS),
and the big ones publish every open job as public JSON - the same data the
careers page itself loads. That is far more complete than job boards for niche
roles, and it is how "scan career pages" tools work.

Supported: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday, Recruitee, Personio.
"""

import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from .job_sources import HEADERS, TIMEOUT, JobLead, SourceError, _clean_html, _get

ATS_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workable": "Workable",
    "smartrecruiters": "SmartRecruiters",
    "workday": "Workday",
    "recruitee": "Recruitee",
    "personio": "Personio",
}

# Big employers list thousands of jobs; for these boards only postings matching the keywords are read in full
MAX_DETAILED = 60

# careers-page URL pattern -> ATS. The captured groups form the company's board token.
_URL_PATTERNS = [
    (re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([\w-]+)"), "greenhouse"),
    (re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)"), "ashby"),
    (re.compile(r"apply\.workable\.com/([\w-]+)"), "workable"),
    (re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)"), "smartrecruiters"),
    # Workday token is "tenant/wdN/site", e.g. nvidia/wd5/NVIDIAExternalCareerSite
    (re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)"), "workday"),
    (re.compile(r"([\w-]+)\.recruitee\.com"), "recruitee"),
    (re.compile(r"([\w-]+)\.jobs\.personio\.(?:de|com)"), "personio"),
]
_NOT_TOKENS = {"j", "jobs", "embed", "api", "www", "app", "careers", "job", "en", "wday", "oneclick-ui"}


def detect_board(url: str) -> tuple[str, str] | None:
    """Return (ats, token) for a careers-page URL hosted on a supported ATS."""
    for pattern, ats in _URL_PATTERNS:
        match = pattern.search(url or "")
        if match and not any(g.lower() in _NOT_TOKENS for g in match.groups()):
            return ats, "/".join(match.groups())
    return None


def _keyword_hit(text: str, keywords: list[str]) -> bool:
    from .matcher import has_keyword

    low = (text or "").lower()
    return not keywords or any(has_keyword(k, low) for k in keywords)


def find_board_on_page(url: str) -> tuple[str, str] | None:
    """Open a company's own careers page and look for a link or embed pointing at an ATS."""
    if detect := detect_board(url):
        return detect
    if not urlparse(url).scheme:
        url = f"https://{url}"
    try:
        page = _get(url).text
    except SourceError:
        return None
    for match in re.finditer(r"https?://[^\s\"'<>]+", page):
        if detect := detect_board(match.group(0)):
            return detect
    return None


def _greenhouse(token: str, company: str) -> list[JobLead]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"}).json()
    return [
        JobLead(
            company=company or j.get("company_name") or token,
            job_title=j.get("title", ""),
            job_url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            source="Greenhouse",
            description=_clean_html(html.unescape(j.get("content") or ""), 6000),
        )
        for j in data.get("jobs", [])
    ]


def _lever(token: str, company: str) -> list[JobLead]:
    data = _get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"}).json()
    leads = []
    for j in data:
        lists = " ".join(f"{part.get('text', '')} {_clean_html(part.get('content', ''), 3000)}" for part in j.get("lists") or [])
        leads.append(
            JobLead(
                company=company or token,
                job_title=j.get("text", ""),
                job_url=j.get("hostedUrl", ""),
                location=(j.get("categories") or {}).get("location") or j.get("workplaceType") or "",
                source="Lever",
                description=re.sub(r"\s+", " ", f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')}")[:6000],
            )
        )
    return leads


def _ashby(token: str, company: str) -> list[JobLead]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}").json()
    return [
        JobLead(
            company=company or token,
            job_title=j.get("title", ""),
            job_url=j.get("jobUrl", ""),
            location=("Remote" if j.get("isRemote") else "") or j.get("location", ""),
            source="Ashby",
            description=re.sub(r"\s+", " ", j.get("descriptionPlain") or "")[:6000],
        )
        for j in data.get("jobs", [])
        if j.get("isListed", True)
    ]


def _workable(token: str, company: str) -> list[JobLead]:
    data = _get(f"https://apply.workable.com/api/v1/widget/accounts/{token}", params={"details": "true"}).json()
    leads = []
    for j in data.get("jobs", []):
        place = ", ".join(p for p in (j.get("city"), j.get("country")) if p)
        leads.append(
            JobLead(
                company=company or data.get("name") or token,
                job_title=j.get("title", ""),
                job_url=j.get("url") or j.get("shortlink", ""),
                location="Remote" if str(j.get("telecommuting")).lower() == "true" else place,
                source="Workable",
                description=_clean_html(j.get("description") or "", 6000),
            )
        )
    return leads


def _smartrecruiters(token: str, company: str, keywords: list[str]) -> list[JobLead]:
    base = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
    first = _get(base, params={"limit": 100}).json()
    postings = first.get("content", [])
    if first.get("totalFound", 0) > 100:            # large employer: let SmartRecruiters search for us
        postings, seen = [], set()
        for kw in keywords or [""]:
            for p in _get(base, params={"limit": 100, "q": kw}).json().get("content", []):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    postings.append(p)
    postings = [p for p in postings if _keyword_hit(p.get("name"), keywords)][:MAX_DETAILED] or postings[:MAX_DETAILED]

    def detail(p: dict) -> JobLead:
        try:
            d = _get(f"{base}/{p['id']}").json()
            sections = (d.get("jobAd") or {}).get("sections") or {}
            text = " ".join(_clean_html((sections.get(k) or {}).get("text", ""), 3000) for k in ("jobDescription", "qualifications"))
            url = d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{token}/{p['id']}"
        except SourceError:
            text, url = "", f"https://jobs.smartrecruiters.com/{token}/{p['id']}"
        loc = p.get("location") or {}
        level = (p.get("experienceLevel") or {}).get("label", "")
        return JobLead(
            company=company or (p.get("company") or {}).get("name") or token,
            job_title=p.get("name", ""),
            job_url=url,
            location="Remote" if loc.get("remote") else ", ".join(x for x in (loc.get("city"), (loc.get("country") or "").upper()) if x),
            source="SmartRecruiters",
            description=f"{level}. {text}"[:6000],
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(detail, postings))


def _workday(token: str, company: str, keywords: list[str]) -> list[JobLead]:
    tenant, wd, site = token.split("/")
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{host}/wday/cxs/{tenant}/{site}"
    found, seen = [], set()
    for kw in keywords or [""]:
        try:
            resp = requests.post(f"{api}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": kw},
                                 headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise SourceError(str(e)) from e
        for p in resp.json().get("jobPostings", []):
            if p.get("externalPath") and p["externalPath"] not in seen:
                seen.add(p["externalPath"])
                found.append(p)
    found = found[:MAX_DETAILED]

    def detail(p: dict) -> JobLead:
        try:
            info = _get(f"{api}{p['externalPath']}").json().get("jobPostingInfo", {})
            text = _clean_html(info.get("jobDescription", ""), 6000)
        except SourceError:
            text = ""
        return JobLead(
            company=company or tenant.replace("-", " ").title(),
            job_title=p.get("title", ""),
            job_url=f"{host}/{site}{p['externalPath']}",
            location=p.get("locationsText", ""),
            source="Workday",
            description=text,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(detail, found))


def _recruitee(token: str, company: str, keywords: list[str]) -> list[JobLead]:
    data = _get(f"https://{token}.recruitee.com/api/offers/").json()
    return [
        JobLead(
            company=company or o.get("company_name") or token,
            job_title=o.get("title", ""),
            job_url=o.get("careers_url", ""),
            location="Remote" if o.get("remote") else o.get("location") or o.get("city") or "",
            source="Recruitee",
            description=_clean_html(f"{o.get('experience_code', '')} {o.get('description', '')} {o.get('requirements', '')}", 6000),
        )
        for o in data.get("offers", [])
    ]


def _personio(token: str, company: str, keywords: list[str]) -> list[JobLead]:
    root = ET.fromstring(_get(f"https://{token}.jobs.personio.de/xml").content)
    leads = []
    for pos in root.iter("position"):
        get = lambda tag: (pos.findtext(tag) or "").strip()
        body = " ".join(_clean_html(v.text or "", 3000) for v in pos.iter("value"))
        years = get("yearsOfExperience")
        leads.append(
            JobLead(
                company=company or get("subcompany") or token,
                job_title=get("name"),
                job_url=f"https://{token}.jobs.personio.de/job/{get('id')}",
                location=get("office"),
                source="Personio",
                description=f"{get('seniority')} {years + ' years of experience.' if years else ''} {body}"[:6000],
            )
        )
    return leads


_FETCHERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby, "workable": _workable}
_SEARCHING_FETCHERS = {"smartrecruiters": _smartrecruiters, "workday": _workday, "recruitee": _recruitee, "personio": _personio}


def fetch_jobs(ats: str, token: str, company: str = "", keywords: list[str] | None = None) -> list[JobLead]:
    """Open jobs on one company's board. Keywords narrow the search on boards of very large employers."""
    try:
        if ats in _FETCHERS:
            leads = _FETCHERS[ats](token, company)
        elif ats in _SEARCHING_FETCHERS:
            leads = _SEARCHING_FETCHERS[ats](token, company, keywords or [])
        else:
            raise SourceError(f"Unsupported job board: {ats}")
        return [lead for lead in leads if lead.job_title]
    except (ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as e:
        raise SourceError(f"Unexpected response from {ATS_NAMES.get(ats, ats)}: {e}") from e


def board_name(ats: str, token: str) -> str:
    """Best-effort company name for a board, used when it's added without one."""
    pretty = token.split("/")[0].replace("-", " ").replace("_", " ").title()
    try:
        if ats == "greenhouse":
            return _get(f"https://boards-api.greenhouse.io/v1/boards/{token}").json().get("name") or pretty
        if ats == "workable":
            return _get(f"https://apply.workable.com/api/v1/widget/accounts/{token}").json().get("name") or pretty
        if ats == "smartrecruiters":
            items = _get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", params={"limit": 1}).json().get("content", [])
            return (items[0].get("company") or {}).get("name", pretty) if items else pretty
        if ats == "recruitee":
            offers = _get(f"https://{token}.recruitee.com/api/offers/").json().get("offers", [])
            return offers[0].get("company_name", pretty) if offers else pretty
    except (SourceError, ValueError, KeyError, IndexError):
        pass
    return pretty


# Starter watchlists of companies whose boards are public (verified October 2026).
# "tech" suits any software, data, design or product role - scans only keep jobs matching the user's keywords.
TECH_STARTER = [
    {"name": "Razorpay", "ats": "greenhouse", "token": "razorpaysoftwareprivatelimited", "website": "https://razorpay.com"},
    {"name": "Groww", "ats": "greenhouse", "token": "groww", "website": "https://groww.in"},
    {"name": "CRED", "ats": "lever", "token": "cred", "website": "https://cred.club"},
    {"name": "Meesho", "ats": "lever", "token": "meesho", "website": "https://meesho.com"},
    {"name": "Zeta", "ats": "lever", "token": "zeta", "website": "https://www.zeta.tech"},
    {"name": "InMobi", "ats": "greenhouse", "token": "inmobi", "website": "https://www.inmobi.com"},
    {"name": "Freshworks", "ats": "smartrecruiters", "token": "Freshworks", "website": "https://www.freshworks.com"},
    {"name": "Databricks", "ats": "greenhouse", "token": "databricks", "website": "https://www.databricks.com"},
    {"name": "MongoDB", "ats": "greenhouse", "token": "mongodb", "website": "https://www.mongodb.com"},
    {"name": "GitLab", "ats": "greenhouse", "token": "gitlab", "website": "https://about.gitlab.com"},
    {"name": "Stripe", "ats": "greenhouse", "token": "stripe", "website": "https://stripe.com"},
    {"name": "Airbnb", "ats": "greenhouse", "token": "airbnb", "website": "https://www.airbnb.com"},
    {"name": "Coinbase", "ats": "greenhouse", "token": "coinbase", "website": "https://www.coinbase.com"},
    {"name": "Twilio", "ats": "greenhouse", "token": "twilio", "website": "https://www.twilio.com"},
    {"name": "Figma", "ats": "greenhouse", "token": "figma", "website": "https://www.figma.com"},
    {"name": "Salesforce", "ats": "workday", "token": "salesforce/wd12/External_Career_Site", "website": "https://www.salesforce.com"},
    {"name": "Visa (early careers)", "ats": "workday", "token": "visa/wd5/Visa_Early_Careers", "website": "https://www.visa.co.in"},
    {"name": "Nvidia", "ats": "workday", "token": "nvidia/wd5/NVIDIAExternalCareerSite", "website": "https://www.nvidia.com"},
    {"name": "Atlan", "ats": "ashby", "token": "atlan", "website": "https://atlan.com"},
    {"name": "Notion", "ats": "ashby", "token": "notion", "website": "https://www.notion.so"},
    {"name": "Vercel", "ats": "greenhouse", "token": "vercel", "website": "https://vercel.com"},
    {"name": "Cloudflare", "ats": "greenhouse", "token": "cloudflare", "website": "https://www.cloudflare.com"},
]

# AI-security and AI-safety companies
AI_SECURITY_STARTER = [
    {"name": "Apollo Research", "ats": "lever", "token": "apolloresearch", "website": "https://www.apolloresearch.ai"},
    {"name": "Haize Labs", "ats": "greenhouse", "token": "haizelabs", "website": "https://haizelabs.com"},
    {"name": "HiddenLayer", "ats": "greenhouse", "token": "hiddenlayer", "website": "https://hiddenlayer.com"},
    {"name": "Trail of Bits", "ats": "workable", "token": "trailofbits", "website": "https://www.trailofbits.com"},
    {"name": "Bishop Fox", "ats": "greenhouse", "token": "bishopfox", "website": "https://bishopfox.com"},
    {"name": "CloudSEK", "ats": "greenhouse", "token": "cloudsek", "website": "https://www.cloudsek.com"},
    {"name": "METR", "ats": "lever", "token": "metr", "website": "https://metr.org"},
    {"name": "Redwood Research", "ats": "ashby", "token": "redwoodresearch", "website": "https://www.redwoodresearch.org"},
    {"name": "Scale AI", "ats": "greenhouse", "token": "scaleai", "website": "https://scale.com"},
    {"name": "Anthropic", "ats": "greenhouse", "token": "anthropic", "website": "https://www.anthropic.com"},
    {"name": "OpenAI", "ats": "ashby", "token": "openai", "website": "https://openai.com"},
    {"name": "Cohere", "ats": "ashby", "token": "cohere", "website": "https://cohere.com"},
]

STARTER_LISTS = {
    "tech": ("Popular tech companies", TECH_STARTER),
    "ai_security": ("AI security & safety companies", AI_SECURITY_STARTER),
}
