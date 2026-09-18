"""Stanford Faculty Positions (facultypositions.stanford.edu).

Search: /jobs/search?query=oncology&page=N ; each detail page has a JobPosting JSON-LD block.
Stanford's clinical faculty ranges are stated in the description (California law).
"""
from __future__ import annotations

import json
import logging
import re

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

BASE = "https://facultypositions.stanford.edu"
QUERIES = ["oncology", "hematology", "cancer"]
_LINK_RE = re.compile(r'href="(?:https://facultypositions\.stanford\.edu)?(/jobs/[a-z0-9][^"?#]*)"')
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def fetch() -> list[dict]:
    links: dict[str, None] = {}
    for q in QUERIES:
        for page in range(1, 6):
            r = http.get(f"{BASE}/jobs/search?query={q}&page={page}")
            if r is None or r.status_code != 200:
                break
            found = [BASE + u for u in _LINK_RE.findall(r.text) if not u.startswith("/jobs/search")]
            new = [u for u in found if u not in links]
            for u in new:
                links[u] = None
            if not new:
                break
    jobs = []
    for url in links:
        r = http.get(url)
        if r is None or r.status_code != 200:
            continue
        ld = None
        for m in _LD_RE.finditer(r.text):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                ld = d
                break
        if not ld:
            continue
        desc_html = ld.get("description") or ""
        jobs.append({
            "source": "stanford",
            "source_name": "Stanford Faculty Positions",
            "source_url": url,
            "external_id": url.rsplit("/", 1)[-1][:80],
            "title": squash(ld.get("title")),
            "employer": "Stanford University",
            "location_text": "Stanford, CA",
            "city": "Stanford", "state_text": "CA",
            "posted_date": (ld.get("datePosted") or "")[:10] or None,
            "closing_date": (ld.get("validThrough") or "")[:10] or None,
            "employment_type": None,
            "salary_text": None,
            "education_text": None,
            "position_text": None,
            "description_html": desc_html,
            "description_text": html_to_text(desc_html),
        })
    log.info("Stanford Faculty Positions: %d postings", len(jobs))
    return jobs
