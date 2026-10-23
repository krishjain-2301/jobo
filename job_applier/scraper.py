"""Find a company's website, then its hiring email and careers page.

Only public pages are read (home, contact, careers, about), robots.txt is
respected and at most a handful of pages per company are fetched.
"""

import difflib
import re
from functools import lru_cache
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 JobDedo/1.0"
}
TIMEOUT = 12
MAX_PAGES = 8

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
OBFUSCATED_RE = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*[\[\(\{]\s*at\s*[\]\)\}]\s*([A-Za-z0-9-]+)\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*([A-Za-z]{2,24})",
    re.I,
)

# Sites that show up in search results but are never the company's own site
NOT_COMPANY_SITES = {
    "linkedin.com", "glassdoor.com", "glassdoor.co.in", "indeed.com", "in.indeed.com",
    "wikipedia.org", "crunchbase.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "naukri.com", "ambitionbox.com", "remotive.com",
    "remoteok.com", "arbeitnow.com", "adzuna.com", "adzuna.in", "jooble.org",
    "bloomberg.com", "zoominfo.com", "github.com", "medium.com", "reddit.com",
    "quora.com", "wellfound.com", "angel.co", "tracxn.com", "zaubacorp.com",
    "justdial.com", "simplyhired.com", "monster.com", "foundit.in", "shine.com",
    "internshala.com", "cutshort.io", "instahyre.com", "builtin.com", "ycombinator.com",
    "dnb.com", "owler.com", "pitchbook.com", "apollo.io", "rocketreach.co", "signalhire.com",
}

# Applicant tracking systems: a link to one of these is the "apply here" page
ATS_HOSTS = (
    "greenhouse.io", "lever.co", "workable.com", "ashbyhq.com", "smartrecruiters.com",
    "myworkdayjobs.com", "bamboohr.com", "recruitee.com", "zohorecruit", "keka.com",
    "darwinbox", "freshteam.com", "teamtailor.com", "personio", "breezy.hr", "jobvite.com",
    "icims.com", "successfactors", "taleo.net", "jazzhr.com", "rippling.com",
)

PAGE_KEYWORDS = ("career", "jobs", "job", "join", "hiring", "work-with-us", "contact", "about", "team")
DEFAULT_PATHS = ("/careers", "/contact", "/contact-us", "/jobs", "/about")

JUNK_EMAIL_DOMAINS = (
    "example.com", "example.org", "domain.com", "email.com", "yourdomain", "sentry.io",
    "sentry-next", "wixpress.com", "wix.com", "godaddy.com", "mysite.com", "company.com",
    "ingest.sentry", "users.noreply.github.com", "cloudflare.com",
)
JUNK_LOCAL_PARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "privacy", "abuse", "postmaster",
    "webmaster", "unsubscribe", "legal", "dpo", "gdpr", "security", "billing", "invoice",
    "accounts", "compliance", "dmca", "mailer-daemon",
)
HIRING_WORDS = ("career", "job", "hr", "recruit", "talent", "hiring", "people", "join", "resume", "cv", "apply", "intern")
GENERAL_WORDS = ("hello", "contact", "info", "team", "office", "admin", "enquir", "inquir", "connect", "hi")
LOW_WORDS = ("support", "help", "sales", "press", "media", "marketing", "partner", "investor", "pr")

FREE_MAIL = ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me", "protonmail.com")


def _domain(url: str) -> str:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _root(domain: str) -> str:
    """'careers.acme.co.in' -> 'acme'"""
    parts = [p for p in domain.split(".") if p not in ("www", "com", "co", "in", "io", "org", "net", "ai", "uk", "de")]
    return max(parts, key=len) if parts else domain


def _looks_like_company(name: str, domain: str) -> bool:
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split() if len(w) >= 3]
    root = _root(domain)
    squashed = "".join(words)
    if any(w in domain for w in words) or (squashed and squashed in domain):
        return True
    return difflib.SequenceMatcher(None, squashed, root).ratio() > 0.7


def _blocked(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in NOT_COMPANY_SITES)


def find_website(company: str) -> str | None:
    """Look the company up on DuckDuckGo and return its homepage URL."""
    try:
        from ddgs import DDGS

        results = DDGS().text(f"{company} official website", max_results=8) or []
    except Exception:
        return None
    for r in results:
        href = r.get("href") or ""
        domain = _domain(href)
        if domain and not _blocked(domain) and _looks_like_company(company, domain):
            return f"https://{urlparse(href).netloc}"
    return None


@lru_cache(maxsize=512)
def _robots(base: str) -> robotparser.RobotFileParser | None:
    rp = robotparser.RobotFileParser()
    try:
        resp = requests.get(urljoin(base, "/robots.txt"), headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code >= 400:
            return None
        rp.parse(resp.text.splitlines())
        return rp
    except requests.RequestException:
        return None


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    rp = _robots(f"{parsed.scheme}://{parsed.netloc}")
    return rp is None or rp.can_fetch(HEADERS["User-Agent"], url)


def _fetch(url: str) -> tuple[str, str] | None:
    """Returns (final_url, html) or None."""
    if not _allowed(url):
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", "html"):
        return None
    return resp.url, resp.text


def extract_emails(text: str) -> set[str]:
    found = {m.group(0) for m in EMAIL_RE.finditer(text)}
    found |= {f"{a}@{b}.{c}" for a, b, c in OBFUSCATED_RE.findall(text)}
    clean = set()
    for email in found:
        email = email.strip(".").lower()
        local, _, domain = email.partition("@")
        if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|ico)$", email):
            continue
        if any(j in domain for j in JUNK_EMAIL_DOMAINS) or any(local.startswith(j) for j in JUNK_LOCAL_PARTS):
            continue
        if re.fullmatch(r"[0-9a-f]{16,}", local):  # tracking hashes
            continue
        clean.add(email)
    return clean


def score_email(email: str, company_domain: str | None, from_job_post: bool = False) -> int:
    local, _, domain = email.partition("@")
    score = 30
    if any(w in local for w in HIRING_WORDS):
        score = 100
    elif any(local.startswith(w) for w in GENERAL_WORDS):
        score = 50
    elif any(local.startswith(w) for w in LOW_WORDS):
        score = 10
    if company_domain:
        if domain == company_domain or domain.endswith("." + company_domain) or company_domain.endswith("." + domain):
            score += 20
        elif domain not in FREE_MAIL:
            score -= 30
    if from_job_post:
        score += 40
    return score


def rank_emails(emails: set[str], company_domain: str | None, job_post_emails: set[str] = frozenset()) -> list[str]:
    return sorted(
        emails | set(job_post_emails),
        key=lambda e: score_email(e, company_domain, e in job_post_emails),
        reverse=True,
    )


def scrape_contacts(website: str) -> dict:
    """Crawl a few pages of the site. Returns {"emails": set, "careers_url": str|None}."""
    base = website if "://" in website else f"https://{website}"
    home = _fetch(base)
    if not home:
        return {"emails": set(), "careers_url": None}
    home_url, html = home
    site_domain = _domain(home_url)

    emails: set[str] = set()
    careers_url = None
    to_visit: list[str] = []

    def harvest(page_url: str, page_html: str) -> None:
        nonlocal careers_url
        soup = BeautifulSoup(page_html, "html.parser")
        for a in soup.select("a[href^='mailto:']"):
            emails.update(extract_emails(a["href"][7:].split("?")[0]))
        emails.update(extract_emails(soup.get_text(" ")))
        for a in soup.find_all("a", href=True):
            link = urljoin(page_url, a["href"]).split("#")[0]
            low = (link + " " + a.get_text(" ", strip=True)).lower()
            host = _domain(link)
            if careers_url is None and any(h in host for h in ATS_HOSTS):
                careers_url = link
            if host.endswith(site_domain) and any(k in low for k in PAGE_KEYWORDS):
                if link not in to_visit and link.rstrip("/") != home_url.rstrip("/"):
                    to_visit.append(link)

    harvest(home_url, html)
    # Most promising pages first: careers/jobs, then contact, then the rest
    to_visit.sort(key=lambda u: 0 if re.search(r"career|job|join|hiring", u, re.I) else 1 if "contact" in u.lower() else 2)
    to_visit += [urljoin(home_url, p) for p in DEFAULT_PATHS if urljoin(home_url, p) not in to_visit]

    visited = 0
    for url in to_visit:
        if visited >= MAX_PAGES:
            break
        page = _fetch(url)
        visited += 1
        if not page:
            continue
        final_url, page_html = page
        if careers_url is None and re.search(r"career|jobs|join-us|hiring", final_url, re.I):
            careers_url = final_url
        harvest(final_url, page_html)

    return {"emails": emails, "careers_url": careers_url}


def find_contacts(company: dict) -> dict:
    """Fill website / emails / careers_url for one company row."""
    website = company.get("website") or find_website(company["name"])
    job_post_emails = extract_emails(company.get("job_description") or "")
    scraped = scrape_contacts(website) if website else {"emails": set(), "careers_url": None}
    ranked = rank_emails(scraped["emails"], _domain(website) if website else None, job_post_emails)
    return {
        "website": website,
        "emails": ranked,
        "email": ranked[0] if ranked else None,
        "careers_url": scraped["careers_url"],
    }
