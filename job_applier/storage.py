"""SQLite storage for companies, drafts and the sent-mail log."""

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# JOB_DEDO_DATA_DIR points the app at another folder, e.g. a demo profile that keeps your own data separate
DATA_DIR = Path(os.environ.get("JOB_DEDO_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
DB_PATH = DATA_DIR / "job_applier.db"

# Lifecycle of a company row
NEW = "new"                # found by a search, contacts not looked up yet
READY = "ready"            # has an email address, no draft yet
NO_EMAIL = "no_email"      # no email found - apply through the link instead
DRAFTED = "drafted"        # subject/body written, waiting for review
APPROVED = "approved"      # reviewed, will be sent
SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"
PORTAL = "portal"          # found on a company's own job board - apply through its form, not by email
APPLIED = "applied"        # applied through the job posting's form (marked by the user)

STATUSES = [NEW, PORTAL, READY, NO_EMAIL, DRAFTED, APPROVED, SENT, APPLIED, FAILED, SKIPPED]

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    website TEXT,
    job_title TEXT,
    job_url TEXT,
    job_description TEXT,
    location TEXT,
    source TEXT,
    emails TEXT DEFAULT '[]',
    email TEXT,
    careers_url TEXT,
    status TEXT DEFAULT 'new',
    subject TEXT,
    body TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ats TEXT NOT NULL,
    token TEXT NOT NULL,
    website TEXT,
    last_scanned TEXT,
    jobs_total INTEGER,
    jobs_matched INTEGER,
    error TEXT,
    UNIQUE (ats, token)
);
CREATE TABLE IF NOT EXISTS sent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    company TEXT,
    email TEXT,
    subject TEXT,
    sent_at TEXT
);
"""

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|pvt|private|plc|gmbh|corp|corporation|co|company|ag|sa|bv|srl)\b"
)


# Columns added after the first release - added to old databases on connect
MIGRATIONS = {
    "match_score": "INTEGER",
    "match_level": "TEXT",
    "matched": "TEXT DEFAULT '[]'",
    "missing": "TEXT DEFAULT '[]'",
}
JSON_COLUMNS = ("emails", "matched", "missing")
# Statuses where the company hasn't been emailed or drafted yet, so a better job can replace the stored one
REPLACEABLE = (NEW, PORTAL, READY, NO_EMAIL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def name_key(name: str) -> str:
    """Normalise a company name so "Acme Pvt. Ltd." and "ACME" dedupe together."""
    key = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    key = _SUFFIXES.sub(" ", key)
    return re.sub(r"\s+", " ", key).strip() or name.lower().strip()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(companies)")}
    for column, kind in MIGRATIONS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE companies ADD COLUMN {column} {kind}")
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for column in JSON_COLUMNS:
        if column in d:
            d[column] = json.loads(d.get(column) or "[]")
    return d


def add_company(conn, company: dict) -> bool:
    """Insert a company; returns False if it already exists."""
    key = name_key(company["name"])
    if conn.execute("SELECT 1 FROM companies WHERE name_key = ?", (key,)).fetchone():
        return False
    emails = company.get("emails") or ([company["email"]] if company.get("email") else [])
    conn.execute(
        """INSERT INTO companies (name, name_key, website, job_title, job_url, job_description,
           location, source, emails, email, careers_url, status, created_at, updated_at,
           match_score, match_level, matched, missing)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            company["name"].strip(),
            key,
            company.get("website"),
            company.get("job_title"),
            company.get("job_url"),
            company.get("job_description"),
            company.get("location"),
            company.get("source"),
            json.dumps(emails),
            company.get("email"),
            company.get("careers_url"),
            company.get("status", READY if company.get("email") else NEW),
            _now(),
            _now(),
            company.get("match_score"),
            company.get("match_level"),
            json.dumps(company.get("matched") or []),
            json.dumps(company.get("missing") or []),
        ),
    )
    conn.commit()
    return True


def upsert_lead(conn, company: dict) -> str:
    """Add a job lead, or swap in this job if it fits better than the one stored for the company.

    Returns "added", "updated" or "kept".
    """
    if add_company(conn, company):
        return "added"
    row = conn.execute("SELECT * FROM companies WHERE name_key = ?", (name_key(company["name"]),)).fetchone()
    if row["status"] not in REPLACEABLE or (row["match_score"] or 0) >= (company.get("match_score") or 0):
        return "kept"
    fields = ("job_title", "job_url", "job_description", "location", "source", "match_score", "match_level", "matched", "missing")
    update_company(conn, row["id"], **{f: company.get(f) for f in fields})
    if company.get("website") and not row["website"]:
        update_company(conn, row["id"], website=company["website"])
    return "updated"


def update_company(conn, company_id: int, **fields) -> None:
    if not fields:
        return
    for column in JSON_COLUMNS:
        if column in fields:
            fields[column] = json.dumps(fields[column] or [])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE companies SET {cols} WHERE id = ?", (*fields.values(), company_id))
    conn.commit()


def get_companies(conn, statuses: list[str] | None = None) -> list[dict]:
    if statuses:
        marks = ",".join("?" * len(statuses))
        rows = conn.execute(
            f"SELECT * FROM companies WHERE status IN ({marks}) ORDER BY id", statuses
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM companies ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_companies(conn, ids: list[int]) -> None:
    conn.executemany("DELETE FROM companies WHERE id = ?", [(i,) for i in ids])
    conn.commit()


def status_counts(conn) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM companies GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def log_sent(conn, company: dict, subject: str) -> None:
    conn.execute(
        "INSERT INTO sent_log (company_id, company, email, subject, sent_at) VALUES (?, ?, ?, ?, ?)",
        (company["id"], company["name"], company["email"].lower(), subject, _now()),
    )
    conn.commit()


def already_emailed(conn, email: str) -> bool:
    return bool(
        conn.execute("SELECT 1 FROM sent_log WHERE email = ?", (email.lower(),)).fetchone()
    )


def sent_in_last_24h(conn) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    return conn.execute("SELECT COUNT(*) FROM sent_log WHERE sent_at >= ?", (since,)).fetchone()[0]


def sent_log(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM sent_log ORDER BY id DESC").fetchall()]


def get_company(conn, company_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return _row_to_dict(row) if row else None


# ---------------------------------------------------------------- watchlist
def get_watchlist(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM watchlist ORDER BY name COLLATE NOCASE").fetchall()]


def add_watch(conn, name: str, ats: str, token: str, website: str | None = None) -> bool:
    try:
        conn.execute(
            "INSERT INTO watchlist (name, ats, token, website) VALUES (?, ?, ?, ?)", (name.strip(), ats, token, website)
        )
    except sqlite3.IntegrityError:
        return False
    conn.commit()
    return True


def update_watch(conn, watch_id: int, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE watchlist SET {cols} WHERE id = ?", (*fields.values(), watch_id))
    conn.commit()


def delete_watch(conn, watch_id: int) -> None:
    conn.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,))
    conn.commit()
