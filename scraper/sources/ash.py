"""ASH Job Center (jobcenter.hematology.org).

The RSS feed at /rss/jobs.aspx carries every active posting with its full
description. The detail page adds structured metadata (Company/Institution,
Location, Degree Requirements, Salary, Job Type, Job Setting, Application Period).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

BASE = "https://jobcenter.hematology.org"
RSS = f"{BASE}/rss/jobs.aspx"
_ID_RE = re.compile(r"/jobr?/(\d+)")
_META_LABELS = ["Company/Institution", "Location", "Degree Requirements", "Salary", "Job Type",
                "Posted", "Job Setting", "Application Period", "Position Type", "Specialty"]


def _detail_meta(html: str) -> dict:
    text = html_to_text(html)
    meta = {}
    for label in _META_LABELS:
        m = re.search(re.escape(label) + r"\s*:?\s*\n?\s*([^\n]+)", text)
        if m:
            val = squash(m.group(1))
            # Stop at the next label if two ended up on the same line.
            for other in _META_LABELS:
                if other != label and other in val:
                    val = val.split(other)[0].strip(" :")
            meta[label] = val
    return meta


def fetch() -> list[dict]:
    r = http.get(RSS)
    if r is None or r.status_code != 200:
        log.warning("ASH RSS unavailable")
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        log.warning("ASH RSS parse error: %s", e)
        return []
    jobs = []
    for it in root.findall(".//item"):
        link = it.findtext("link") or ""
        m = _ID_RE.search(link)
        if not m:
            continue
        jid = m.group(1)
        url = f"{BASE}/job/{jid}"
        desc_html = it.findtext("description") or ""
        meta = {}
        dr = http.get(url)
        if dr is not None and dr.status_code == 200:
            meta = _detail_meta(dr.text)
        loc = meta.get("Location", "")
        posted = None
        pd = it.findtext("pubDate") or meta.get("Posted")
        if pd:
            posted = _parse_date(pd)
        closing = None
        ap = meta.get("Application Period", "")
        if "-" in ap:
            closing = _parse_date(ap.split("-")[-1].strip())
        salary = meta.get("Salary")
        if salary and salary.lower().startswith("not"):
            salary = None
        jobs.append({
            "source": "ash",
            "source_name": "ASH Job Center",
            "source_url": url,
            "external_id": jid,
            "title": squash(it.findtext("title")),
            "employer": meta.get("Company/Institution"),
            "location_text": loc,
            "city": None, "state_text": None,
            "posted_date": posted,
            "closing_date": closing,
            "employment_type": meta.get("Job Type"),
            "salary_text": salary,
            "education_text": meta.get("Degree Requirements"),
            "position_text": meta.get("Job Setting"),
            "description_html": desc_html,
            "description_text": html_to_text(desc_html),
        })
    log.info("ASH Job Center: %d jobs", len(jobs))
    return jobs


def _parse_date(s: str) -> str | None:
    from email.utils import parsedate_to_datetime
    from datetime import datetime
    s = s.strip()
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:  # noqa: BLE001
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None
