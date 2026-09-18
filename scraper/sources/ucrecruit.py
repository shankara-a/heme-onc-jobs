"""University of California academic recruitments ("UC Recruit").

Each campus runs the same app. /apply lists every open recruitment as a
<tr id="JPF..." data-search="title|ids|department"> row; the detail page /JPFxxxxx
has the description, requirements and (per California law) the salary range.
"""
from __future__ import annotations

import logging
import re

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

CAMPUSES = [
    {"key": "ucsf", "name": "UCSF", "host": "aprecruit.ucsf.edu", "city": "San Francisco"},
    {"key": "ucla", "name": "UCLA", "host": "recruit.apo.ucla.edu", "city": "Los Angeles"},
    {"key": "ucsd", "name": "UC San Diego", "host": "apol-recruit.ucsd.edu", "city": "La Jolla"},
    {"key": "ucdavis", "name": "UC Davis", "host": "recruit.ucdavis.edu", "city": "Sacramento"},
    {"key": "uci", "name": "UC Irvine", "host": "recruit.ap.uci.edu", "city": "Orange"},
]
_ROW_RE = re.compile(r'<tr id="(JPF\d+)"[^>]*data-search="([^"]*)"')
_MATCH_RE = re.compile(r"hematolog|oncolog|leukemia|lymphoma|myeloma|bone marrow|cell therapy|cancer", re.I)
_CLOSE_RE = re.compile(r"Final date:\s*[A-Za-z]+,?\s*([A-Za-z]{3} \d{1,2}, \d{4})")
_OPEN_RE = re.compile(r"Open date:\s*([A-Za-z]+ \d{1,2}, \d{4})")
_LOC_RE = re.compile(r"Job location\s*\n?\s*([^\n]+)")
_ACRONYMS = {"ucla", "ucsf", "ucsd", "uci", "uc", "hs", "hscp", "gi", "gu", "bmt", "md", "phd", "ii", "iii", "iv",
             "cns", "hcc", "vacchcs", "va", "nci", "cll", "aml", "mds", "car-t", "hpv", "ad", "ent"}


def smart_title(s: str) -> str:
    def fix(m):
        w = m.group(0)
        if w.lower() in _ACRONYMS:
            return w.upper()
        return w.lower() if len(w) <= 2 and w.lower() in ("of", "or", "in", "to", "at", "on", "a", "an") else w.capitalize()
    t = re.sub(r"[A-Za-z][A-Za-z'\-]*", fix, s)
    return t[0].upper() + t[1:] if t else t


def clean_location(s: str, default_city: str) -> str:
    """'San Francisco, CA or Oakland, CA' -> 'San Francisco, CA'; strip campus names."""
    s = re.split(r"\s+(?:or|and|/)\s+|;", s)[0]
    s = re.sub(r"^(?:UCLA|UCSF|UCSD|UC Davis|UC Irvine|UC San Diego|UCI)\s*[-–,]?\s*", "", s, flags=re.I).strip(" ,")
    return s if re.search(r"[A-Za-z]", s) else f"{default_city}, CA"


def _date(s: str | None) -> str | None:
    from datetime import datetime
    if not s:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_campus(c: dict) -> list[dict]:
    r = http.get(f"https://{c['host']}/apply")
    if r is None or r.status_code != 200:
        log.warning("UC Recruit %s unavailable", c["name"])
        return []
    seen, jobs = set(), []
    for jpf, search in _ROW_RE.findall(r.text):
        if jpf in seen or not _MATCH_RE.search(search):
            continue
        seen.add(jpf)
        url = f"https://{c['host']}/{jpf}"
        dr = http.get(url)
        if dr is None or dr.status_code != 200:
            continue
        html = dr.text
        title = smart_title(squash(html_to_text(search.split("|")[0])))
        text = html_to_text(html)
        # Trim boilerplate: keep from "Position" section to the "About" / footer.
        start = text.find("Position")
        end = max(text.find("About UC"), text.find("About the University"), text.find("Job location"))
        body = text[start:end] if start >= 0 and end > start else text
        loc_m = _LOC_RE.search(text)
        dept = search.split("|")[-1].replace("&amp;", "&").strip()
        jobs.append({
            "source": f"ucrecruit_{c['key']}",
            "source_name": f"{c['name']} (UC Recruit)",
            "source_url": url,
            "external_id": jpf,
            "title": title,
            "employer": c["name"],
            "location_text": clean_location(squash(loc_m.group(1)), c["city"]) if loc_m else f"{c['city']}, CA",
            "city": None, "state_text": "CA",
            "posted_date": _date((_OPEN_RE.search(text) or [None, None])[1]),
            "closing_date": _date((_CLOSE_RE.search(text) or [None, None])[1]),
            "employment_type": None,
            "salary_text": None,
            "education_text": None,
            "position_text": dept.title(),
            "description_html": None,
            "description_text": body.strip(),
        })
    log.info("UC Recruit %s: %d heme/onc-ish recruitments", c["name"], len(jobs))
    return jobs


def fetch() -> list[dict]:
    jobs = []
    for c in CAMPUSES:
        try:
            jobs.extend(fetch_campus(c))
        except Exception as e:  # noqa: BLE001
            log.warning("UC Recruit %s failed: %s", c["name"], e)
    return jobs
