"""Turn LinkedIn / Naukri / Indeed / Glassdoor / Internshala job-alert emails into job leads.

You set up job alerts on those sites as usual; they email you new matching jobs.
This reads those emails from your own Gmail over IMAP (read-only, with the same
App Password used for sending) and pulls out each job's title, company and link.
The job sites themselves are never visited.
"""

import email
import imaplib
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from urllib.parse import unquote, urlparse, urlunparse

from bs4 import BeautifulSoup

from .job_sources import JobLead

# sender domain -> (label, link pattern of a job posting, how to tidy the link).
# Links are often wrapped in click trackers; the pattern is also matched against the URL-decoded link.
PROVIDERS = {
    "linkedin.com": ("LinkedIn", re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)"), lambda m: f"https://www.linkedin.com/jobs/view/{m.group(1)}/"),
    "naukri.com": ("Naukri", re.compile(r"naukri\.com/(?:jd/)?job-listings-[^?\s\"'&]+"), lambda m: "https://www." + m.group(0)),
    "indeed.com": ("Indeed", re.compile(r"indeed\.[\w.]+/(?:rc/clk|viewjob|pagead/clk|m/viewjob)[^\s\"']*"), lambda m: "https://" + m.group(0)),
    "glassdoor": ("Glassdoor", re.compile(r"glassdoor\.[\w.]+/(?:job-listing|partner/jobListing)[^\s\"'?]*"), lambda m: "https://www." + m.group(0)),
    "internshala.com": ("Internshala", re.compile(r"internshala\.com/(internship|job)/detail/[^?\s\"'/]+"), lambda m: "https://" + m.group(0)),
}
GENERIC_LINK_TEXT = re.compile(
    r"^(view( all)?( job| jobs)?|apply( now)?|see (all|more)( jobs)?|easy apply|save|more|unsubscribe|manage alerts?|show more|jobs?|"
    r"view all recommendations|get app|actively hiring|be an early applicant|promoted|new|no fixed duration|work from office)$",
    re.I,
)
NOISE = re.compile(r"(school alumni|applicants?|connections?|reviews?|^\d+(\.\d+)?$|^\d+ (days?|hours?) ago$|^posted)", re.I)
SEPARATORS = re.compile(r"\s+[·•|–]\s+|\s+-\s+")
YEARS_IN_SLUG = re.compile(r"(\d{1,2})-to-(\d{1,2})-years?")


# Gmail search per site, so invitations, newsletters and quizzes from the same senders are skipped
GMAIL_QUERIES = {
    "linkedin.com": "from:(jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com OR jobs-listings@linkedin.com)",
    "naukri.com": "from:naukri.com (subject:job OR subject:jobs OR subject:requirement OR subject:opportunities OR subject:hiring OR subject:vacancy OR subject:recommended OR subject:intern)",
    "indeed.com": "from:indeed.com",
    "glassdoor": "from:glassdoor",
    "internshala.com": "from:internshala.com (subject:opportunities OR subject:hiring OR subject:internship OR subject:internships OR subject:jobs)",
}
FETCH_BATCH = 15


class AlertError(Exception):
    pass


def _search_ids(imap: imaplib.IMAP4_SSL, domain: str, days: int, since: str) -> list[bytes]:
    """Message ids of recent alert emails from one site (Gmail search syntax, plain IMAP as a fallback)."""
    try:
        status, data = imap.search(None, "X-GM-RAW", f'"{GMAIL_QUERIES[domain]} newer_than:{days}d"')
    except imaplib.IMAP4.error:   # not Gmail
        status, data = imap.search(None, "SINCE", since, "FROM", f'"{domain}"')
    return data[0].split() if status == "OK" and data and data[0] else []


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except (UnicodeDecodeError, LookupError):
        return value or ""


def _html_of(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    return ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _useful(text: str) -> bool:
    return bool(text) and len(text) < 140 and not GENERIC_LINK_TEXT.match(text) and not NOISE.search(text)


def parse_alert(html: str, provider: str) -> list[JobLead]:
    """Pull job cards out of one alert email.

    A job card is a link to the posting. Its text (or the text right after it) reads
    title, then "Company · Location" or company and location on separate lines.
    Each posting usually has several links (logo, title, button); the richest one wins.
    """
    label, pattern, tidy = PROVIDERS[provider]
    soup = BeautifulSoup(html, "html.parser")
    best: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        match = pattern.search(a["href"]) or pattern.search(unquote(a["href"]))
        if not match:
            continue
        url = tidy(match)
        key = urlunparse(urlparse(url)._replace(query="", fragment=""))
        parts = [t for t in (_clean(s) for s in a.stripped_strings) if _useful(t)]
        if len(parts) < 2:   # title-only link: the company is in the text that follows
            parts = parts[:1] + [t for t in (_clean(s) for s in a.find_all_next(string=True, limit=10)) if _useful(t) and t not in parts][:2]
        if not parts:
            continue
        title, rest = parts[0], parts[1:]
        company, location = "", ""
        if rest:
            pieces = SEPARATORS.split(rest[0], maxsplit=1)
            company = pieces[0]
            location = pieces[1] if len(pieces) > 1 else (rest[1] if len(rest) > 1 else "")
        if not company or len(title) < 3:
            continue
        if provider == "internshala.com" and match.group(1) == "internship" and "intern" not in title.lower():
            title += " Internship"
        if location.lower() in ("internship", "intern"):  # Naukri campus alerts list the job type where the place would be
            location = ""
            if "intern" not in title.lower():
                title += " (Internship)"
        extra = ""
        if years := YEARS_IN_SLUG.search(url):          # Naukri puts the experience range in the link
            extra = f" {years.group(1)} to {years.group(2)} years experience."
        candidate = {"title": title, "company": company, "location": location, "url": url, "text": " ".join(parts) + extra}
        if key not in best or len(candidate["text"]) > len(best[key]["text"]):
            best[key] = candidate
    return [
        JobLead(
            company=c["company"][:80],
            job_title=c["title"][:140],
            job_url=c["url"],
            location=c["location"][:80],
            source=f"{label} alert",
            description=c["text"],
        )
        for c in best.values()
    ]


def fetch_alert_jobs(address: str, app_password: str, days: int = 14, max_emails: int = 150, progress=None) -> tuple[list[JobLead], dict[str, int]]:
    """Read recent alert emails from Gmail (read-only). Returns (leads, {provider label: emails read})."""
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        imap.login(address.strip(), app_password.replace(" ", ""))
    except imaplib.IMAP4.error:
        raise AlertError("Gmail refused the login. Check the Gmail address and App Password in Settings, and that IMAP is enabled in Gmail settings.")
    except OSError as e:
        raise AlertError(f"Couldn't reach Gmail: {e}")
    try:
        # All Mail catches alerts that were archived or filed under a category
        status, _ = imap.select('"[Gmail]/All Mail"', readonly=True)
        if status != "OK":
            imap.select("INBOX", readonly=True)
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        leads, counts = [], {}
        for domain, (label, _, _) in PROVIDERS.items():
            if progress:
                progress(f"Reading {label} alerts")
            ids = _search_ids(imap, domain, days, since)[-max_emails:]
            counts[label] = len(ids)
            for i in range(0, len(ids), FETCH_BATCH):   # one round trip per batch, not per email
                status, parts = imap.fetch(b",".join(ids[i:i + FETCH_BATCH]), "(BODY.PEEK[])")   # PEEK: don't mark as read
                if status != "OK":
                    continue
                for part in parts:
                    if isinstance(part, tuple):
                        html = _html_of(email.message_from_bytes(part[1]))
                        if html:
                            leads.extend(parse_alert(html, domain))
        return leads, counts
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
