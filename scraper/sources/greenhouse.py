"""Greenhouse-hosted career boards (oncology biotech / diagnostics).

Public JSON, no auth:  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
Find a company's token in its careers URL: boards.greenhouse.io/{token} or job-boards.greenhouse.io/{token}.
"""
from __future__ import annotations

import html as htmllib
import logging
import re

from .. import http
from ..text import html_to_text, squash

log = logging.getLogger(__name__)

BOARDS = [
    ("natera", "Natera"), ("revolutionmedicines", "Revolution Medicines"), ("nurix", "Nurix Therapeutics"),
    ("summittherapeutics", "Summit Therapeutics"), ("kymeratherapeutics", "Kymera Therapeutics"), ("erasca", "Erasca"),
    ("lyellimmunopharma", "Lyell Immunopharma"), ("xairatherapeutics", "Xaira Therapeutics"), ("freenome", "Freenome"),
    ("flatironhealth", "Flatiron Health"), ("relaytherapeutics", "Relay Therapeutics"), ("nuvalent", "Nuvalent"),
    ("blueprintmedicines", "Blueprint Medicines"), ("arvinas", "Arvinas"), ("veracyte", "Veracyte"),
    ("abcellera", "AbCellera"), ("primemedicine", "Prime Medicine"), ("alumis", "Alumis"),
]
TITLE_FILTER = re.compile(
    r"medical director|physician|clinical development|clinical scien|medical monitor|\(MD\)|\bMD\b|"
    r"medical (?:head|expert|lead|advisor|affairs)|chief medical|safety (?:physician|officer)|therapeutic area",
    re.I,
)
TITLE_EXCLUDE = re.compile(r"representative|sales|program management|project manager|\bmanager\b(?!.*director)|assistant\b|coordinator|intern\b", re.I)
US_RE = re.compile(r"United States|\bUSA?\b|Remote|, [A-Z]{2}\b|California|Massachusetts|New York|Texas|Washington", re.I)


def fetch_board(token: str, name: str) -> list[dict]:
    d = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    if not d:
        return []
    jobs = []
    for j in d.get("jobs", []):
        title = j.get("title") or ""
        if not TITLE_FILTER.search(title) or TITLE_EXCLUDE.search(title):
            continue
        loc = ((j.get("location") or {}).get("name")) or ""
        if loc and not US_RE.search(loc):
            continue
        desc_html = htmllib.unescape(j.get("content") or "")
        jobs.append({
            "source": f"greenhouse_{token}",
            "source_name": name,
            "source_url": j.get("absolute_url"),
            "external_id": str(j.get("id")),
            "title": squash(title),
            "employer": name,
            "location_text": loc,
            "city": None, "state_text": None,
            "posted_date": (j.get("updated_at") or j.get("first_published") or "")[:10] or None,
            "closing_date": None,
            "employment_type": None,
            "salary_text": None,
            "education_text": None,
            "position_text": None,
            "description_html": desc_html,
            "description_text": html_to_text(desc_html),
        })
    log.info("Greenhouse %s: %d physician-flavoured US jobs", name, len(jobs))
    return jobs


def fetch() -> list[dict]:
    jobs = []
    for token, name in BOARDS:
        try:
            jobs.extend(fetch_board(token, name))
        except Exception as e:  # noqa: BLE001
            log.warning("Greenhouse %s failed: %s", name, e)
    return jobs
