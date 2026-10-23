"""Find new companies to watch by searching the web for their job boards.

Most companies' job pages live on a handful of applicant tracking systems, so a
search like  site:jobs.lever.co security intern  turns up companies hiring for
that role that you have never heard of. Each hit is mapped back to the
company's board, which ats.py can then read in full.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .ats import ATS_NAMES, detect_board

# The domain each ATS serves job pages from (what we put after site:)
ATS_DOMAINS = {
    "greenhouse": "boards.greenhouse.io",
    "lever": "jobs.lever.co",
    "ashby": "jobs.ashbyhq.com",
    "workable": "apply.workable.com",
    "smartrecruiters": "jobs.smartrecruiters.com",
    "workday": "myworkdayjobs.com",
    "recruitee": "recruitee.com",
    "personio": "jobs.personio.de",
}
# Search backends tried in order; each one sometimes rate-limits, so fall through to the next
BACKENDS = ("duckduckgo", "bing", "yahoo")


def _search(query: str, max_results: int = 20) -> list[dict]:
    from ddgs import DDGS

    for backend in BACKENDS:
        try:
            results = DDGS().text(query, max_results=max_results, backend=backend) or []
            if results:
                return results
        except Exception:  # rate limited or blocked - try the next backend
            continue
    return []


def discover_boards(
    keywords: list[str],
    location: str = "",
    known: set[tuple[str, str]] = frozenset(),
    progress: Callable[[str, int, int], None] | None = None,
    max_keywords: int = 6,
) -> list[dict]:
    """Search every ATS domain for each keyword. Returns one entry per company board found."""
    boards: dict[tuple[str, str], dict] = {}
    queries = [(kw, ats, dom) for kw in keywords[:max_keywords] for ats, dom in ATS_DOMAINS.items()]
    done = 0
    lock = threading.Lock()

    def run(query: tuple[str, str, str]) -> None:
        nonlocal done
        kw, ats, dom = query
        results = _search(f"site:{dom} {kw} {location}".strip())
        time.sleep(0.3)  # stay polite to the search engines
        with lock:
            for r in results:
                board = detect_board(r.get("href", ""))
                if not board:
                    continue
                entry = boards.setdefault(
                    board,
                    {"ats": board[0], "token": board[1], "hits": 0, "samples": [], "url": r.get("href", ""), "known": board in known},
                )
                entry["hits"] += 1
                title = (r.get("title") or "").split(" - ")[0].split(" | ")[0].strip()
                if title and title not in entry["samples"] and len(entry["samples"]) < 3:
                    entry["samples"].append(title[:90])
            done += 1
            if progress:
                progress(f'Searched {ATS_NAMES[ats]} for "{kw}" · {len(boards)} boards so far', done, len(queries))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(run, queries))
    return sorted(boards.values(), key=lambda b: (b["known"], -b["hits"]))
