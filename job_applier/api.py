"""REST API behind the web UI.

Run with:  python run.py   (serves the API and the built web app on http://localhost:8000)
"""

import csv
from collections import Counter
import io
import random
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import alerts, ats, discovery
from . import matcher
from . import settings as cfg
from . import storage as db
from .job_sources import ADZUNA_COUNTRIES, JobLead, SourceError, search_all
from .mailer import Mailer, MailError
from .resume import extract_text
from .scraper import find_contacts
from .tasks import Task, TaskManager
from .writer import DEFAULT_BODY, DEFAULT_SUBJECT, PLACEHOLDERS, PROVIDERS, WriterError, generate_email, render_template

ROOT = Path(__file__).resolve().parent.parent
WEB_DIST = ROOT / "web" / "dist"
RESUME_DIR = db.DATA_DIR / "resume"
BOARDS = ["Remotive", "RemoteOK", "Arbeitnow", "Adzuna", "Jooble", "JSearch"]

app = FastAPI(title="Job Dedo", docs_url="/api/docs", openapi_url="/api/openapi.json")
tasks = TaskManager()


def conn():
    return db.connect()


def profile() -> dict:
    p = cfg.load_profile()
    # No keywords saved yet: suggest them from the target role, so the filters work for any field
    p["keywords"] = p.get("keywords") or ", ".join(matcher.suggest_keywords(p.get("target_role", "")))
    return p


def resume_path() -> Path | None:
    path = Path(profile()["resume_path"]) if profile().get("resume_path") else None
    return path if path and path.exists() else None


@lru_cache(maxsize=4)
def _resume_cached(path: str, mtime: float) -> tuple[str, frozenset[str]]:
    text = extract_text(path)
    return text, frozenset(matcher.extract_skills(text))


def resume_info() -> tuple[str, frozenset[str]]:
    path = resume_path()
    return _resume_cached(str(path), path.stat().st_mtime) if path else ("", frozenset())


def sender_profile() -> dict:
    p = profile()
    return {**p, "email": p.get("email") or cfg.secret("GMAIL_ADDRESS")}


def _public_company(c: dict) -> dict:
    c = dict(c)
    c.pop("name_key", None)
    c["job_description"] = (c.get("job_description") or "")[:1500]
    return c


# ---------------------------------------------------------------- state & settings
@app.get("/api/state")
def state():
    c = conn()
    p = profile()
    _, skills = resume_info()
    sent_24h = db.sent_in_last_24h(c)
    gmail_ok = bool(cfg.secret("GMAIL_ADDRESS") and cfg.secret("GMAIL_APP_PASSWORD"))
    rpath = resume_path()
    return {
        "profile": {k: v for k, v in p.items() if k not in ("subject_template", "body_template")},
        "suggested_keywords": ", ".join(matcher.suggest_keywords(p.get("target_role", ""))),
        "starter_lists": {key: {"label": label, "count": len(items)} for key, (label, items) in ats.STARTER_LISTS.items()},
        "secrets": {k: bool(cfg.secret(k)) for k in cfg.SECRET_KEYS},
        "gmail_address": cfg.secret("GMAIL_ADDRESS"),
        "resume": {"name": rpath.name if rpath else None, "skills": sorted(skills)},
        "counts": db.status_counts(c),
        "sent_total": len(db.sent_log(c)),
        "sent_24h": sent_24h,
        "allowance": max(0, int(p["daily_limit"]) - sent_24h),
        "checks": {
            "resume": rpath is not None,
            "profile": bool(p["name"] and p["target_role"]),
            "gmail": gmail_ok,
        },
        "providers": {name: {"models": info.get("models", []), "needs_base_url": bool(info.get("needs_base_url"))} for name, info in PROVIDERS.items()},
        "boards": [b for b in BOARDS if b in ("Remotive", "RemoteOK", "Arbeitnow")
                   or (b == "Adzuna" and cfg.secret("ADZUNA_APP_ID") and cfg.secret("ADZUNA_APP_KEY"))
                   or (b == "Jooble" and cfg.secret("JOOBLE_API_KEY"))
                   or (b == "JSearch" and cfg.secret("JSEARCH_API_KEY"))],
        "countries": list(ADZUNA_COUNTRIES),
        "tasks": [t.to_dict() for t in tasks.recent()],
    }


class ProfileIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    target_role: str | None = None
    pitch: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    daily_limit: int | None = None
    delay_min: int | None = None
    delay_max: int | None = None
    keywords: str | None = None
    min_match: int | None = None
    fresher_only: bool | None = None


@app.put("/api/profile")
def save_profile(body: ProfileIn):
    p = cfg.load_profile()
    p.update({k: v for k, v in body.model_dump().items() if v is not None})
    if p["delay_max"] < p["delay_min"]:
        p["delay_max"] = p["delay_min"]
    cfg.save_profile(p)
    return state()


class SecretsIn(BaseModel):
    values: dict[str, str]
    remember: bool = True


@app.put("/api/secrets")
def save_secrets(body: SecretsIn):
    for key, value in body.values.items():
        if key in cfg.SECRET_KEYS and value.strip():
            cfg.set_secret(key, value.strip(), body.remember)
    return state()


@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".docx"):
        raise HTTPException(400, "Upload a PDF or DOCX file.")
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for old in RESUME_DIR.iterdir():
        old.unlink()
    dest = RESUME_DIR / Path(file.filename).name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    p = cfg.load_profile()
    p["resume_path"] = str(dest)
    cfg.save_profile(p)
    return state()


# ---------------------------------------------------------------- tasks
@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "No such task")
    return task.to_dict()


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "No such task")
    task.cancel()
    return task.to_dict()


# ---------------------------------------------------------------- discover
def _score_and_store(task: Task, leads: list[JobLead], websites: dict[str, str] | None = None, title_only: bool = False) -> dict:
    """title_only: leads that come with little or no description (job-alert emails). The minimum match is
    skipped for them - you chose those alerts - but the keyword and seniority filters still apply."""
    """Score leads against the resume, keep the best job per company, store those that pass the filters."""
    p = profile()
    _, skills = resume_info()
    keywords = matcher.parse_keywords(p["keywords"])
    c = conn()
    results, best = [], {}
    for lead in leads:
        m = matcher.score_job(set(skills), keywords, lead.job_title, lead.description)
        row = {
            "company": lead.company,
            "title": lead.job_title,
            "url": lead.job_url,
            "location": lead.location,
            "source": lead.source,
            "score": m.score,
            "level": m.level,
            "matched": m.matched,
            "missing": m.missing,
            "passed": matcher.passes(m, 0 if title_only else int(p["min_match"]), bool(p["fresher_only"])),
            "status": "hidden",
        }
        results.append((row, lead))
        key = db.name_key(lead.company)
        if row["passed"] and (key not in best or best[key][0]["score"] < row["score"]):
            best[key] = (row, lead)

    added = updated = 0
    for row, lead in best.values():
        outcome = db.upsert_lead(c, _lead_record(row, lead, (websites or {}).get(lead.company)))
        row["status"] = outcome
        added += outcome == "added"
        updated += outcome == "updated"
    for row, _ in results:
        if row["passed"] and row["status"] == "hidden":
            row["status"] = "other"  # passed, but another job at the same company fits better
    ordered = sorted((r for r, _ in results), key=lambda r: (not r["passed"], -r["score"]))
    task.step(f"{len(best)} companies matched · {added} new · {updated} updated", len(leads), len(leads))
    return {
        "found": len(leads),
        "passed": sum(r["passed"] for r in ordered),
        "companies": len(best),
        "added": added,
        "updated": updated,
        "jobs": ordered[:300],
        "passed_by_company": dict(Counter(r["company"] for r in ordered if r["passed"])),
    }


def _is_portal(source: str) -> bool:
    """Jobs from a company's own board, a job alert or JSearch are applied for on the posting, not by email."""
    return source in ats.ATS_NAMES.values() or source.endswith(" alert") or source.startswith("JSearch")


def _lead_record(row: dict, lead: JobLead, website: str | None) -> dict:
    return {
        # Jobs read from a company's own board are applied for through that board's form
        **({"status": db.PORTAL} if _is_portal(lead.source) else {}),
        "name": lead.company,
        "website": website,
        "job_title": lead.job_title,
        "job_url": lead.job_url,
        "job_description": lead.description,
        "location": lead.location,
        "source": lead.source,
        "match_score": row["score"],
        "match_level": row["level"],
        "matched": row["matched"],
        "missing": row["missing"],
    }


class BoardSearchIn(BaseModel):
    query: str
    location: str = ""
    country: str = "India"
    sources: list[str] = []
    limit: int = 50


@app.post("/api/discover/boards")
def search_boards(body: BoardSearchIn):
    if not body.query.strip():
        raise HTTPException(400, "Enter a job title or keywords.")

    def run(task: Task):
        task.step("Searching job boards…", 0, 1)
        leads, errors = search_all(
            body.query.strip(),
            body.location.strip(),
            body.sources or state()["boards"],
            body.limit,
            {k: cfg.secret(k) for k in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY", "JSEARCH_API_KEY")},
            ADZUNA_COUNTRIES.get(body.country, "in"),
        )
        task.step(f"Scoring {len(leads)} jobs against your resume…")
        result = _score_and_store(task, leads)
        result["errors"] = errors
        return result

    return tasks.start("discover", f"Job boards: {body.query}", run).to_dict()


class ScanIn(BaseModel):
    ids: list[int] = []


@app.post("/api/discover/scan")
def scan_watchlist(body: ScanIn):
    def run(task: Task):
        c = conn()
        watch = [w for w in db.get_watchlist(c) if not body.ids or w["id"] in body.ids]
        if not watch:
            raise ValueError("Your watchlist is empty - add a company's careers page first.")
        leads, websites, errors = [], {}, {}
        _, skills = resume_info()
        keywords = matcher.parse_keywords(profile()["keywords"])
        p = profile()
        task.step(f"Scanning {len(watch)} career pages…", 0, len(watch))

        def scan_one(w: dict) -> tuple[dict, list[JobLead] | None, str]:
            try:
                return w, ats.fetch_jobs(w["ats"], w["token"], w["name"], keywords), ""
            except SourceError as e:
                return w, None, str(e)

        # boards are independent, so read several at once; results are written from this thread only
        scanned = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(scan_one, w) for w in watch]
            for i, fut in enumerate(as_completed(futures), 1):
                w, found, error = fut.result()
                if found is None:
                    errors[w["name"]] = error
                    db.update_watch(c, w["id"], last_scanned=db._now(), error=error[:300])
                else:
                    scanned.append((w, len(found)))
                    leads.extend(found)
                    websites[w["name"]] = w.get("website")
                task.step(f"Scanned {w['name']} ({ats.ATS_NAMES[w['ats']]}) · {len(leads)} jobs so far", i)
        task.step(f"Scoring {len(leads)} jobs against your resume…", len(watch), len(watch))
        result = _score_and_store(task, leads, websites)
        matched = result.pop("passed_by_company")
        for w, total in scanned:
            db.update_watch(c, w["id"], last_scanned=db._now(), jobs_total=total, jobs_matched=matched.get(w["name"], 0), error=None)
        result["errors"] = errors
        return result

    return tasks.start("discover", "Career page scan", run).to_dict()


class LeadIn(BaseModel):
    company: str
    title: str
    url: str = ""
    location: str = ""
    source: str = ""
    score: int = 0
    level: str = ""
    matched: list[str] = []
    missing: list[str] = []


@app.post("/api/discover/add")
def add_lead_anyway(body: LeadIn):
    """Add a job the filters hid ("add anyway")."""
    lead = JobLead(body.company, body.title, body.url, body.location, body.source)
    outcome = db.upsert_lead(conn(), _lead_record(body.model_dump(), lead, None))
    return {"status": outcome}


# ---------------------------------------------------------------- watchlist
@app.get("/api/watchlist")
def watchlist():
    return db.get_watchlist(conn())


class WatchIn(BaseModel):
    url: str
    name: str = ""


@app.post("/api/watchlist")
def add_watch(body: WatchIn):
    board = ats.find_board_on_page(body.url.strip())
    if not board:
        raise HTTPException(
            400,
            "Couldn't find a Greenhouse, Lever, Ashby or Workable job board at that link. "
            "Open the company's careers page, click any job, and paste that job's link instead.",
        )
    kind, token = board
    try:
        jobs = ats.fetch_jobs(kind, token, body.name, matcher.parse_keywords(profile()["keywords"]))
    except SourceError as e:
        raise HTTPException(400, f"Found a {ats.ATS_NAMES[kind]} board '{token}', but couldn't read it: {e}")
    name = body.name.strip() or ats.board_name(kind, token)
    site = None if ats.detect_board(body.url) else body.url.strip()
    if not db.add_watch(conn(), name, kind, token, site):
        raise HTTPException(409, f"{name} is already on your watchlist.")
    return {"name": name, "ats": kind, "token": token, "jobs": len(jobs)}


class WebFindIn(BaseModel):
    keywords: str = ""
    location: str = ""


@app.post("/api/discover/web")
def discover_web(body: WebFindIn):
    """Search the web for company job boards matching the keywords (site: searches across every ATS)."""
    keywords = matcher.parse_keywords(body.keywords or profile()["keywords"])
    if not keywords:
        raise HTTPException(400, "Add some role keywords first.")

    def run(task: Task):
        known = {(w["ats"], w["token"]) for w in db.get_watchlist(conn())}
        boards = discovery.discover_boards(keywords, body.location.strip(), known, lambda m, d, t: task.step(m, d, t))
        new = sum(not b["known"] for b in boards)
        task.step(f"Found {len(boards)} company job boards, {new} new.", task.total, task.total)
        return {"boards": boards, "new": new}

    return tasks.start("webfind", "Finding companies on the web", run).to_dict()


class BoardIn(BaseModel):
    ats: str
    token: str


class BulkWatchIn(BaseModel):
    boards: list[BoardIn]
    scan: bool = True


@app.post("/api/watchlist/bulk")
def add_watch_bulk(body: BulkWatchIn):
    """Add several discovered boards (names are looked up in parallel), then optionally scan just those."""
    wanted = [b for b in body.boards if b.ats in ats.ATS_NAMES]
    if not wanted:
        raise HTTPException(400, "Pick at least one company.")
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(pool.map(lambda b: ats.board_name(b.ats, b.token), wanted))
    c = conn()
    added = [b for b, name in zip(wanted, names) if db.add_watch(c, name, b.ats, b.token)]
    ids = [w["id"] for w in db.get_watchlist(c) if (w["ats"], w["token"]) in {(b.ats, b.token) for b in wanted}]
    result = {"added": len(added)}
    if body.scan and ids:
        result["task"] = scan_watchlist(ScanIn(ids=ids))
    return result


class AlertsIn(BaseModel):
    days: int = 14


@app.post("/api/discover/alerts")
def import_alerts(body: AlertsIn):
    """Read LinkedIn / Naukri / Indeed / Glassdoor / Internshala job-alert emails from Gmail and score the jobs."""
    gmail, password = cfg.secret("GMAIL_ADDRESS"), cfg.secret("GMAIL_APP_PASSWORD")
    if not (gmail and password):
        raise HTTPException(400, "Connect your Gmail (address + App Password) in Settings first - alerts are read from your inbox.")

    def run(task: Task):
        task.step("Connecting to Gmail…", 0, 1)
        leads, counts = alerts.fetch_alert_jobs(gmail, password, max(1, min(60, body.days)), progress=lambda m: task.step(m))
        if not leads:
            emails = sum(counts.values())
            raise ValueError(
                f"Read {emails} alert emails from the last {body.days} days but found no jobs in them. "
                "Set up job alerts on LinkedIn, Naukri or Indeed first (see the steps on this page)."
                if not emails else
                f"Read {emails} alert emails but couldn't pick jobs out of them - their email layout may have changed."
            )
        task.step(f"Scoring {len(leads)} jobs from {sum(counts.values())} alert emails…")
        result = _score_and_store(task, leads, title_only=True)
        result["errors"] = {}
        result["providers"] = counts
        return result

    return tasks.start("discover", "Importing job alerts from Gmail", run).to_dict()


class StarterIn(BaseModel):
    list: str = "tech"


@app.post("/api/watchlist/starter")
def add_starter_watchlist(body: StarterIn):
    if body.list not in ats.STARTER_LISTS:
        raise HTTPException(400, "Unknown starter list.")
    c = conn()
    added = sum(db.add_watch(c, w["name"], w["ats"], w["token"], w["website"]) for w in ats.STARTER_LISTS[body.list][1])
    return {"added": added}


@app.delete("/api/watchlist/{watch_id}")
def delete_watch(watch_id: int):
    db.delete_watch(conn(), watch_id)
    return {"ok": True}


# ---------------------------------------------------------------- companies
@app.get("/api/companies")
def companies():
    return [_public_company(c) for c in db.get_companies(conn())]


class CompanyIn(BaseModel):
    name: str
    website: str = ""
    email: str = ""
    job_title: str = ""
    job_url: str = ""


@app.post("/api/companies")
def add_company(body: CompanyIn):
    if not body.name.strip():
        raise HTTPException(400, "Company name is required.")
    ok = db.add_company(
        conn(),
        {
            "name": body.name,
            "website": body.website.strip() or None,
            "email": body.email.strip().lower() or None,
            "job_title": body.job_title.strip() or None,
            "job_url": body.job_url.strip() or None,
            "source": "Manual",
        },
    )
    if not ok:
        raise HTTPException(409, f"{body.name} is already in your pipeline.")
    return {"ok": True}


class CompanyPatch(BaseModel):
    email: str | None = None
    website: str | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None


@app.patch("/api/companies/{company_id}")
def patch_company(company_id: int, patch: CompanyPatch):
    c = conn()
    orig = db.get_company(c, company_id)
    if not orig:
        raise HTTPException(404, "Company not found")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "status" in fields and fields["status"] not in db.STATUSES:
        raise HTTPException(400, "Unknown status")
    if "email" in fields:
        email = fields["email"].strip().lower()
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise HTTPException(400, "That doesn't look like an email address.")
        fields["email"] = email or None
        fields["emails"] = orig["emails"] if not email or email in orig["emails"] else [email, *orig["emails"]]
        status = fields.get("status", orig["status"])
        if email and status in (db.NEW, db.PORTAL, db.NO_EMAIL):
            fields["status"] = db.READY
        elif not email and status in (db.READY, db.DRAFTED, db.APPROVED):
            fields["status"] = db.NO_EMAIL
    if "website" in fields:
        fields["website"] = fields["website"].strip() or None
    db.update_company(c, company_id, **fields)
    return _public_company(db.get_company(c, company_id))


class IdsIn(BaseModel):
    ids: list[int]


@app.post("/api/companies/delete")
def delete_companies(body: IdsIn):
    c = conn()
    unsent = [i for i in body.ids if (row := db.get_company(c, i)) and row["status"] != db.SENT]
    db.delete_companies(c, unsent)
    return {"deleted": len(unsent)}


@app.post("/api/companies/approve")
def approve(body: IdsIn):
    c = conn()
    n = 0
    for i in body.ids:
        row = db.get_company(c, i)
        if row and row["status"] in (db.DRAFTED, db.FAILED) and row["email"] and row["subject"] and row["body"]:
            db.update_company(c, i, status=db.APPROVED, error=None)
            n += 1
    return {"approved": n}


# ---------------------------------------------------------------- contacts
class LookupIn(BaseModel):
    ids: list[int] = []
    include_no_email: bool = False


@app.post("/api/contacts/lookup")
def lookup_contacts(body: LookupIn):
    def run(task: Task):
        c = conn()
        # Portal jobs are skipped unless picked explicitly - big companies only take applications through their form
        wanted = [db.NEW, db.NO_EMAIL, db.PORTAL] if body.ids else [db.NEW, db.NO_EMAIL] if body.include_no_email else [db.NEW]
        targets = [r for r in db.get_companies(c, wanted) if not body.ids or r["id"] in body.ids]
        if not targets:
            raise ValueError("Nothing to look up - every company already has an email.")
        found = 0
        task.step("Visiting company websites…", 0, len(targets))
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(find_contacts, r): r for r in targets}
            for i, fut in enumerate(as_completed(futures), 1):
                company = futures[fut]
                try:
                    res = fut.result()
                    found += bool(res["email"])
                    db.update_company(c, company["id"], **res, status=db.READY if res["email"] else db.NO_EMAIL, error=None)
                except Exception as e:  # one bad site shouldn't stop the batch
                    db.update_company(c, company["id"], status=db.NO_EMAIL, error=str(e)[:300])
                task.step(f"{company['name']} done", i)
        task.message = f"Emails found for {found} of {len(targets)} companies."
        return {"found": found, "total": len(targets)}

    return tasks.start("contacts", "Finding hiring emails", run).to_dict()


# ---------------------------------------------------------------- compose
@app.get("/api/compose/template")
def get_template():
    p = cfg.load_profile()
    return {
        "subject": p["subject_template"] or DEFAULT_SUBJECT,
        "body": p["body_template"] or DEFAULT_BODY,
        "placeholders": PLACEHOLDERS,
    }


class TemplateIn(BaseModel):
    subject: str
    body: str
    ids: list[int] = []
    company_id: int | None = None


def _render(subject: str, body: str, company: dict) -> tuple[str, str]:
    try:
        return render_template(subject, body, sender_profile(), company)
    except (ValueError, IndexError, KeyError) as e:
        raise HTTPException(400, f"Template problem: {e}. Use {{placeholder}} names from the list.")


@app.post("/api/compose/preview")
def preview(body: TemplateIn):
    c = conn()
    company = (db.get_company(c, body.company_id) if body.company_id else None) or {"name": "Acme Corp", "job_title": "Security Intern"}
    s, b = _render(body.subject, body.body, company)
    return {"subject": s, "body": b}


@app.post("/api/compose/template")
def drafts_from_template(body: TemplateIn):
    c = conn()
    p = cfg.load_profile()
    p.update(subject_template=body.subject, body_template=body.body)
    cfg.save_profile(p)
    n = 0
    for i in body.ids:
        company = db.get_company(c, i)
        if company and company["status"] in (db.READY, db.DRAFTED):
            s, b = _render(body.subject, body.body, company)
            db.update_company(c, i, subject=s, body=b, status=db.DRAFTED, error=None)
            n += 1
    return {"drafted": n}


class AiIn(BaseModel):
    ids: list[int]
    instructions: str = ""


@app.post("/api/compose/ai")
def drafts_with_ai(body: AiIn):
    p = profile()
    provider = p["provider"]
    api_key = cfg.secret(PROVIDERS[provider]["key_env"])
    if not api_key and not PROVIDERS[provider].get("needs_base_url"):
        raise HTTPException(400, f"Add your {provider} API key in Settings to use the AI writer.")
    if not resume_path():
        raise HTTPException(400, "Upload your resume in Settings first.")

    def run(task: Task):
        c = conn()
        text, _ = resume_info()
        targets = [r for r in (db.get_company(c, i) for i in body.ids) if r and r["status"] in (db.READY, db.DRAFTED)]
        written = 0
        for i, company in enumerate(targets):
            task.step(f"Writing to {company['name']}", i, len(targets))
            try:
                s, b = generate_email(provider, api_key, p["model"], sender_profile(), text, company, body.instructions, p.get("base_url"))
                db.update_company(c, company["id"], subject=s, body=b, status=db.DRAFTED, error=None)
                written += 1
            except WriterError as e:
                db.update_company(c, company["id"], error=str(e))
                if i == 0:
                    raise  # the same error would hit every company
        task.step(f"Wrote {written} drafts.", len(targets), len(targets))
        return {"written": written}

    return tasks.start("compose", "Writing emails with AI", run).to_dict()


# ---------------------------------------------------------------- send
def _mailer() -> Mailer:
    p = profile()
    gmail, password = cfg.secret("GMAIL_ADDRESS"), cfg.secret("GMAIL_APP_PASSWORD")
    if not (gmail and password):
        raise HTTPException(400, "Connect your Gmail (address + App Password) in Settings first.")
    return Mailer(gmail, password, p["name"], p["smtp_host"], p["smtp_port"])


class TestIn(BaseModel):
    company_id: int


@app.post("/api/send/test")
def send_test(body: TestIn):
    c = conn()
    company = db.get_company(c, body.company_id)
    rpath = resume_path()
    if not company or not company["body"]:
        raise HTTPException(400, "Pick a company with a written draft.")
    if not rpath:
        raise HTTPException(400, "Upload your resume in Settings first.")
    mailer = _mailer()
    try:
        with mailer as m:
            m.send(mailer.user, f"[TEST → {company['email']}] {company['subject']}", company["body"], rpath)
    except MailError as e:
        raise HTTPException(400, str(e))
    return {"sent_to": mailer.user}


@app.post("/api/send")
def send(body: IdsIn):
    c = conn()
    p = profile()
    rpath = resume_path()
    if not rpath:
        raise HTTPException(400, "Upload your resume in Settings first.")
    mailer = _mailer()
    allowance = max(0, int(p["daily_limit"]) - db.sent_in_last_24h(c))
    batch = [r for r in (db.get_company(c, i) for i in body.ids) if r and r["status"] == db.APPROVED][:allowance]
    if not batch:
        raise HTTPException(400, "Nothing to send - approve some drafts first, or you've hit today's limit.")

    def run(task: Task):
        c = conn()
        sent = skipped = failed = 0
        task.step("Connecting to Gmail…", 0, len(batch))
        with mailer as m:
            for i, company in enumerate(batch, 1):
                task.step(f"Sending to {company['name']}", i - 1)
                if db.already_emailed(c, company["email"]):
                    db.update_company(c, company["id"], status=db.SKIPPED, error="Already emailed this address before")
                    skipped += 1
                else:
                    try:
                        m.send(company["email"], company["subject"], company["body"], rpath)
                        db.log_sent(c, company, company["subject"])
                        db.update_company(c, company["id"], status=db.SENT, error=None)
                        sent += 1
                    except MailError as e:
                        db.update_company(c, company["id"], status=db.FAILED, error=str(e))
                        failed += 1
                task.done = i
                if i < len(batch):
                    wait = random.randint(int(p["delay_min"]), int(p["delay_max"]))
                    for left in range(wait, 0, -1):
                        task.step(f"Next email in {left}s - pausing so Gmail doesn't flag you as spam")
                        task.sleep(1)
        task.step(f"Sent {sent} email{'s' * (sent != 1)}.", len(batch))
        return {"sent": sent, "skipped": skipped, "failed": failed}

    return tasks.start("send", f"Sending {len(batch)} emails", run).to_dict()


# ---------------------------------------------------------------- history & export
@app.get("/api/history")
def history():
    return db.sent_log(conn())


def _csv(rows: list[dict], columns: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ", ".join(v) if isinstance(v, list) else v for k, v in row.items()})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/export/sent.csv")
def export_sent():
    return _csv(db.sent_log(conn()), ["sent_at", "company", "email", "subject"], "sent_log.csv")


@app.get("/api/export/companies.csv")
def export_companies():
    cols = ["name", "status", "match_score", "match_level", "job_title", "job_url", "email", "emails", "website", "careers_url", "source", "created_at"]
    return _csv(db.get_companies(conn()), cols, "companies.csv")


# ---------------------------------------------------------------- web app
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = WEB_DIST / path
        if path and file.is_file() and WEB_DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(WEB_DIST / "index.html")
