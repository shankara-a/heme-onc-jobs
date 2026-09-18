"""Madgex-powered job boards: ASCO Career Center, NEJM CareerCenter, Inside Higher Ed,
Nature Careers, Science Careers.

Both expose a paginated RSS search (`/jobsrss/?keywords=...&countrycode=US&page=N`)
and a detail page carrying a schema.org JobPosting JSON-LD block plus a
<dt>/<dd> sidebar (Employer / Location / Salary / Closing date / Education ...).
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

BOARDS = {
    "asco": {"name": "ASCO Career Center", "base": "https://careercenter.asco.org", "keywords": ["hematology", "oncology"]},
    "nejm": {"name": "NEJM CareerCenter", "base": "https://www.nejmcareercenter.org", "keywords": ["hematology oncology", "hematologist", "oncologist"]},
    "ihe": {"name": "Inside Higher Ed Careers", "base": "https://careers.insidehighered.com", "keywords": ["hematology oncology", "medical oncology", "hematologist"]},
    "nature": {"name": "Nature Careers", "base": "https://www.nature.com/naturecareers", "keywords": ["hematology oncology", "medical oncology"]},
    "science": {"name": "Science Careers", "base": "https://jobs.sciencecareers.org", "keywords": ["hematology oncology", "medical oncology"]},
}

_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_DTDD_RE = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
_JOB_ID_RE = re.compile(r"/job/(\d+)")
MAX_PAGES = 40


def _rss_links(base: str, keywords: str) -> list[tuple[str, str]]:
    """Yield (url, pubDate) for every US result across all RSS pages."""
    out, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{base}/jobsrss/?keywords={keywords.replace(' ', '+')}&countrycode=US&page={page}"
        r = http.get(url)
        if r is None or r.status_code != 200:
            break
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            log.warning("bad RSS from %s", url)
            break
        items = root.findall(".//item")
        if not items:
            break
        new = 0
        for it in items:
            link = (it.findtext("link") or "").split("?")[0]
            jid = _JOB_ID_RE.search(link)
            if not jid or jid.group(1) in seen:
                continue
            seen.add(jid.group(1))
            out.append((link, it.findtext("pubDate") or ""))
            new += 1
        if new == 0 or len(items) < 20:
            break
    return out


def _parse_detail(html: str, url: str, board: dict) -> dict | None:
    ld = None
    for m in _LD_RE.finditer(html):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            ld = d
            break
    if not ld:
        return None
    side = {}
    for k, v in _DTDD_RE.findall(html):
        side[squash(html_to_text(k)).rstrip(":").lower()] = squash(html_to_text(v))

    loc = (ld.get("jobLocation") or [{}])
    if isinstance(loc, dict):
        loc = [loc]
    addr = (loc[0] or {}).get("address", {}) if loc else {}
    city, region, country = addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")
    if country and country.upper() not in ("US", "USA", "UNITED STATES"):
        return None
    org = ld.get("hiringOrganization") or {}
    emp_type = ld.get("employmentType")
    if isinstance(emp_type, list):
        emp_type = ", ".join(emp_type)
    desc_html = ld.get("description") or ""
    return {
        "source": board["key"],
        "source_name": board["name"],
        "source_url": url,
        "external_id": _JOB_ID_RE.search(url).group(1),
        "title": squash(ld.get("title")),
        "employer": squash(org.get("name") or side.get("employer")),
        "location_text": side.get("location") or ", ".join(p for p in [city, region] if p),
        "city": city, "state_text": region,
        "posted_date": (ld.get("datePosted") or "")[:10] or None,
        "closing_date": (ld.get("validThrough") or "")[:10] or None,
        "employment_type": emp_type or side.get("hours"),
        "salary_text": side.get("salary"),
        "education_text": side.get("education"),
        "position_text": side.get("position") or side.get("category"),
        "description_html": desc_html,
        "description_text": html_to_text(desc_html),
    }


def fetch(board_key: str) -> list[dict]:
    board = dict(BOARDS[board_key], key=board_key)
    links: dict[str, str] = {}
    for kw in board["keywords"]:
        for url, pub in _rss_links(board["base"], kw):
            links.setdefault(url, pub)
    log.info("%s: %d unique listings from RSS", board["name"], len(links))
    jobs = []
    for url in links:
        r = http.get(url)
        if r is None or r.status_code != 200:
            continue
        job = _parse_detail(r.text, url, board)
        if job:
            jobs.append(job)
    log.info("%s: %d US job details parsed", board["name"], len(jobs))
    return jobs
