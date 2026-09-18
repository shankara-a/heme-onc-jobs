"""PracticeMatch (practicematch.com) — large physician recruiting board.

Listing: /physicians/jobs/hematology-oncology/?page_id=N  (~31 per page, ordering is
not stable so we collect ids until a page adds nothing new).
Detail:  /physicians/job-details.cfm/{id}/  with a schema.org JobPosting JSON-LD block.
"""
from __future__ import annotations

import json
import logging
import re

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

BASE = "https://www.practicematch.com"
LIST = f"{BASE}/physicians/jobs/hematology-oncology/?page_id={{page}}"
_ID_RE = re.compile(r"/physicians/job-details\.cfm/(\d+)/")
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
MAX_PAGES = 40


def _ids() -> list[str]:
    seen: list[str] = []
    stale = 0
    for page in range(1, MAX_PAGES + 1):
        r = http.get(LIST.format(page=page))
        if r is None or r.status_code != 200:
            break
        ids = [i for i in dict.fromkeys(_ID_RE.findall(r.text)) if i not in seen]
        if not ids:
            stale += 1
            if stale >= 2:
                break
            continue
        stale = 0
        seen.extend(ids)
    return seen


def _detail(jid: str) -> dict | None:
    url = f"{BASE}/physicians/job-details.cfm/{jid}/"
    r = http.get(url)
    if r is None or r.status_code != 200:
        return None
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
        return None
    loc = ld.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address") or {}
    city, region = addr.get("addressLocality"), addr.get("addressRegion")
    org = ld.get("hiringOrganization") or {}
    emp = ld.get("employmentType")
    if isinstance(emp, list):
        emp = ", ".join(emp)
    desc_html = ld.get("description") or ""
    salary = ld.get("baseSalary") or {}
    sal_text = None
    if salary:
        v = salary.get("value") or {}
        if isinstance(v, dict) and (v.get("minValue") or v.get("value")):
            sal_text = f"${v.get('minValue') or v.get('value')} - ${v.get('maxValue') or ''} per {v.get('unitText', 'year')}"
    return {
        "source": "practicematch",
        "source_name": "PracticeMatch",
        "source_url": ld.get("url") or url,
        "external_id": jid,
        "title": squash(ld.get("title")),
        "employer": squash(org.get("name")),
        "location_text": ", ".join(p for p in [city, region] if p),
        "city": city, "state_text": region,
        "posted_date": (ld.get("datePosted") or "")[:10] or None,
        "closing_date": (ld.get("validThrough") or "")[:10] or None,
        "employment_type": emp,
        "salary_text": sal_text,
        "education_text": None,
        "position_text": ld.get("occupationalCategory"),
        "description_html": desc_html,
        "description_text": html_to_text(desc_html),
    }


def fetch() -> list[dict]:
    ids = _ids()
    log.info("PracticeMatch: %d listing ids", len(ids))
    jobs = []
    for jid in ids:
        j = _detail(jid)
        if j:
            jobs.append(j)
    log.info("PracticeMatch: %d job details parsed", len(jobs))
    return jobs
