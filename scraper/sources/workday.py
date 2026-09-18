"""Workday-hosted career sites (industry: Amgen, Gilead/Kite, ...).

Workday exposes an unauthenticated JSON API:
  POST https://{host}/wday/cxs/{tenant}/{site}/jobs   {searchText, limit, offset}
  GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}  -> jobPostingInfo

Add a tenant by appending to TENANTS. Find the three values in any job URL:
  https://amgen.wd1.myworkdayjobs.com/Careers/job/...  ->  host=amgen.wd1..., tenant=amgen, site=Careers
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

TENANTS = [
    {"key": "amgen", "name": "Amgen", "host": "amgen.wd1.myworkdayjobs.com", "tenant": "amgen", "site": "Careers"},
    {"key": "gilead", "name": "Gilead / Kite", "host": "gilead.wd1.myworkdayjobs.com", "tenant": "gilead", "site": "gileadcareers"},
    {"key": "roche", "name": "Roche / Genentech", "host": "roche.wd3.myworkdayjobs.com", "tenant": "roche", "site": "roche-ext"},
    {"key": "bms", "name": "Bristol Myers Squibb", "host": "bristolmyerssquibb.wd5.myworkdayjobs.com", "tenant": "bristolmyerssquibb", "site": "BMS"},
    {"key": "pfizer", "name": "Pfizer", "host": "pfizer.wd1.myworkdayjobs.com", "tenant": "pfizer", "site": "PfizerCareers"},
    {"key": "merck", "name": "Merck", "host": "msd.wd5.myworkdayjobs.com", "tenant": "msd", "site": "SearchJobs"},
    {"key": "astrazeneca", "name": "AstraZeneca", "host": "astrazeneca.wd3.myworkdayjobs.com", "tenant": "astrazeneca", "site": "Careers"},
    {"key": "novartis", "name": "Novartis", "host": "novartis.wd3.myworkdayjobs.com", "tenant": "novartis", "site": "Novartis_Careers"},
    {"key": "sanofi", "name": "Sanofi", "host": "sanofi.wd3.myworkdayjobs.com", "tenant": "sanofi", "site": "SanofiCareers"},
    {"key": "gsk", "name": "GSK", "host": "gsk.wd5.myworkdayjobs.com", "tenant": "gsk", "site": "GSKCareers"},
    {"key": "sharp", "name": "Sharp HealthCare", "host": "sharp.wd1.myworkdayjobs.com", "tenant": "sharp", "site": "External"},
]
SEARCHES = ["hematology", "oncology physician", "oncology medical director", "clinical development oncology"]
PAGE = 20
MAX_RESULTS = 200
# Industry boards return hundreds of non-physician roles; require a physician-flavoured title.
TITLE_FILTER = re.compile(
    r"medical director|physician|clinical development (?:director|lead|head|physician|\(MD\))|"
    r"\(MD\)|\bMD\b|medical monitor|medical (?:head|expert|lead|advisor)|chief medical|"
    r"(?:senior |executive |global )?(?:safety|medical affairs) (?:medical )?director|therapeutic area (?:head|lead)",
    re.I,
)
TITLE_EXCLUDE = re.compile(r"representative|sales|manager\b(?!.*director)|associate director, (?:regulatory|quality|data)|scientist(?!.*\(MD\))|assistant\b", re.I)


def _posted_to_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d+)\+?\s*days?", s, re.I)
    if m:
        return (date.today() - timedelta(days=int(m.group(1)))).isoformat()
    if re.search(r"today", s, re.I):
        return date.today().isoformat()
    if re.search(r"yesterday", s, re.I):
        return (date.today() - timedelta(days=1)).isoformat()
    return None


def _search(t: dict, text: str) -> list[dict]:
    base = f"https://{t['host']}/wday/cxs/{t['tenant']}/{t['site']}"
    out, offset = [], 0
    while offset < MAX_RESULTS:
        d = http.post_json(f"{base}/jobs", {"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": text})
        if not d:
            break
        posts = d.get("jobPostings") or []
        out.extend(posts)
        if len(posts) < PAGE:
            break
        offset += PAGE
    return out


def fetch_tenant(t: dict) -> list[dict]:
    base = f"https://{t['host']}/wday/cxs/{t['tenant']}/{t['site']}"
    seen, jobs = set(), []
    for q in SEARCHES:
        for p in _search(t, q):
            path = p.get("externalPath")
            if not path or path in seen:
                continue
            seen.add(path)
            if not TITLE_FILTER.search(p.get("title", "")) or TITLE_EXCLUDE.search(p.get("title", "")):
                continue
            loc = p.get("locationsText") or ""
            if not re.search(r"United States|USA|\bUS\b|Remote|, [A-Z]{2}\b|California", loc) and loc:
                continue
            d = http.get_json(base + path)
            info = (d or {}).get("jobPostingInfo") or {}
            country = ((info.get("country") or {}).get("descriptor") or "")
            if country and "United States" not in country:
                continue
            desc_html = info.get("jobDescription") or ""
            jobs.append({
                "source": f"workday_{t['key']}",
                "source_name": t["name"],
                "source_url": info.get("externalUrl") or f"https://{t['host']}/{t['site']}{path}",
                "external_id": info.get("jobReqId") or path,
                "title": squash(info.get("title") or p.get("title")),
                "employer": t["name"],
                "location_text": info.get("location") or loc,
                "city": None, "state_text": None,
                "posted_date": info.get("startDate") or _posted_to_date(p.get("postedOn")),
                "closing_date": None,
                "employment_type": info.get("timeType"),
                "salary_text": None,
                "education_text": None,
                "position_text": info.get("remoteType"),
                "description_html": desc_html,
                "description_text": html_to_text(desc_html),
            })
    log.info("Workday %s: %d physician-flavoured US jobs", t["name"], len(jobs))
    return jobs


def fetch() -> list[dict]:
    jobs = []
    for t in TENANTS:
        try:
            jobs.extend(fetch_tenant(t))
        except Exception as e:  # noqa: BLE001
            log.warning("Workday %s failed: %s", t["name"], e)
    return jobs
