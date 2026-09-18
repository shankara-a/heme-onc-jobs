"""Scrape every source, normalize, extract fields, de-duplicate, write data/jobs.json.

Usage:
    python -m scraper.run                 # all sources
    python -m scraper.run --sources asco ash
    python -m scraper.run --limit 20      # quick smoke test (per source)
    python -m scraper.run --no-llm        # skip Claude enrichment even if key is set
    python -m scraper.run --raw-cache /tmp/raw.json   # dev: reuse fetched postings, re-run extraction only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import extract, geo, llm_enrich
from .sources import ash, greenhouse, madgex, practicematch, stanford, ucrecruit, workday
from .text import norm_key, stable_id

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JOBS_PATH = DATA / "jobs.json"
META_PATH = DATA / "meta.json"
LLM_CACHE = DATA / "llm_cache.json"
DESCRIPTION_CAP = 2500

SOURCES = {
    "asco": lambda: madgex.fetch("asco"),
    "nejm": lambda: madgex.fetch("nejm"),
    "ihe": lambda: madgex.fetch("ihe"),
    "nature": lambda: madgex.fetch("nature"),
    "science": lambda: madgex.fetch("science"),
    "ash": ash.fetch,
    "practicematch": practicematch.fetch,
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "ucrecruit": ucrecruit.fetch,
    "stanford": stanford.fetch,
}

log = logging.getLogger("scraper")


def normalize(raw: dict) -> dict | None:
    title, text = raw["title"], raw.get("description_text") or ""
    industry = raw["source"].startswith(("workday", "greenhouse"))
    # General academic boards (IHE/Nature/Science) return anything mentioning oncology,
    # so they get the same strict physician test as industry career sites.
    strict = industry or raw["source"] in ("ihe", "nature", "science")
    if not extract.is_relevant(title, text, require_physician_hint=strict):
        return None
    # Prefer the board's free-text location (the job's location) over JSON-LD
    # address fields, which recruiters often fill with their own HQ.
    city, state = geo.parse_location(raw.get("location_text"))
    if not state:
        city, state = raw.get("city"), geo.state_code(raw.get("state_text"))
    # Recruiter titles ("Hem Onc | Ohio | 4-day week", "... in Southern California")
    # name the real state; the board's location field is often the agency's HQ.
    tcity, tstate = geo.parse_location(title)
    if tstate and tstate != state:
        city, state = tcity, tstate
    elif tstate and tcity and not city:
        city = tcity
    if raw["source"].startswith("ucrecruit"):
        state = "CA"
    if city and (any(ch.isdigit() for ch in city) or len(city) > 30):
        city = None  # recruiter HQ street address, not the job's city
    latlon = geo.coords(city, state)

    jt = extract.classify_job_type(title, raw.get("employer") or "", text)
    if industry and jt["type"] == "unknown":
        jt = {"type": "industry", "confidence": 0.6, "scores": jt["scores"]}
    md = extract.md_required(title, f"{raw.get('education_text') or ''}\n{text}")
    salary = extract.parse_salary(text, raw.get("salary_text"), title)
    benefits = extract.extract_benefits(text)
    effort = extract.parse_effort(text)

    job = {
        "id": stable_id(raw["source"], raw["external_id"]),
        "source": raw["source"],
        "source_name": raw["source_name"],
        "url": raw["source_url"],
        "title": title,
        "employer": raw.get("employer"),
        "location": {"text": raw.get("location_text"), "city": city, "state": state,
                     "lat": latlon[0] if latlon else None, "lon": latlon[1] if latlon else None,
                     "geo_precision": "city" if (latlon and city and (city.lower(), state) in geo.CITY_COORDS) else "state"},
        "remote": extract.remote_flag(title, text, raw.get("location_text")),
        "posted_date": raw.get("posted_date"),
        "closing_date": raw.get("closing_date"),
        "employment_type": raw.get("employment_type"),
        "job_type": jt["type"],
        "job_type_confidence": jt["confidence"],
        "rank": extract.rank(title, text),
        "md_required": md["required"],
        "md_note": md["note"],
        "education_text": raw.get("education_text"),
        "salary": salary or {"min": None, "max": None, "period": None, "text": raw.get("salary_text"), "disclosed": False, "annualized_from": None},
        "effort": effort,
        "benefits": benefits["tags"],
        "benefit_snippets": benefits["snippets"],
        "benefit_amounts": benefits["amounts"],
        "subspecialties": extract.subspecialties(title, text),
        "description": text[:DESCRIPTION_CAP * 2],  # extra kept for de-dup matching; trimmed on output
        "enriched_by": "rules",
    }
    return job


def dedupe(jobs: list[dict]) -> list[dict]:
    """Collapse the same posting seen twice.

    Cross-source (ASCO + NEJM + ASH cross-listings): title + employer + state match.
    Same-source (recruiter reposts): additionally the opening of the description must match.
    """
    by_key: dict[str, dict] = {}
    for j in jobs:
        key = "|".join([norm_key(j["title"])[:40], norm_key(j.get("employer"))[:30], j["location"]["state"] or ""])
        same_text = key in by_key and norm_key(by_key[key]["description"][:300]) == norm_key(j["description"][:300])
        if key in by_key and (by_key[key]["source"] != j["source"] or same_text):
            keep = by_key[key]
            keep.setdefault("also_listed", []).append({"source_name": j["source_name"], "url": j["url"]})
            # Prefer whichever copy has richer structured data.
            if not keep["salary"]["disclosed"] and j["salary"]["disclosed"]:
                keep["salary"] = j["salary"]
            if keep["effort"]["clinical"] is None and j["effort"]["clinical"] is not None:
                keep["effort"] = j["effort"]
            for b in j["benefits"]:
                if b not in keep["benefits"]:
                    keep["benefits"].append(b)
                    keep["benefit_snippets"][b] = j["benefit_snippets"][b]
            if not keep.get("posted_date") and j.get("posted_date"):
                keep["posted_date"] = j["posted_date"]
        elif key in by_key:
            by_key[key + "#" + j["id"]] = j  # same board, distinct req with an identical title
        else:
            by_key[key] = j
    return list(by_key.values())


def merge_history(jobs: list[dict]) -> None:
    """Preserve first_seen / summary from the previous run."""
    if not JOBS_PATH.exists():
        return
    try:
        prev = {j["id"]: j for j in json.loads(JOBS_PATH.read_text()).get("jobs", [])}
    except (ValueError, KeyError):
        return
    today = date.today().isoformat()
    for j in jobs:
        p = prev.get(j["id"])
        j["first_seen"] = p.get("first_seen", today) if p else today
        j["last_seen"] = today


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="*", default=list(SOURCES), choices=list(SOURCES))
    ap.add_argument("--limit", type=int, default=None, help="cap raw jobs per source (smoke tests)")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--raw-cache", type=Path, default=None, help="dev: load raw postings from this file if it exists, else fetch and save there")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    raw_all, stats = [], {}
    if args.raw_cache and args.raw_cache.exists():
        raw_all = json.loads(args.raw_cache.read_text())
        log.info("loaded %d raw postings from %s", len(raw_all), args.raw_cache)
        for r in raw_all:
            src = r["source"].split("_")[0]
            stats.setdefault(src, {"raw": 0})["raw"] += 1
    else:
        for name in args.sources:
            try:
                raw = SOURCES[name]()
            except Exception as e:  # noqa: BLE001
                log.exception("source %s crashed: %s", name, e)
                raw = []
            if args.limit:
                raw = raw[: args.limit]
            stats[name] = {"raw": len(raw)}
            raw_all.extend(raw)
        if args.raw_cache:
            args.raw_cache.write_text(json.dumps(raw_all))

    jobs = []
    for r in raw_all:
        j = normalize(r)
        if j:
            jobs.append(j)
    for name in stats:
        stats[name]["kept"] = sum(1 for j in jobs if j["source"] == name or j["source"].startswith(name + "_"))
    log.info("relevant physician heme/onc jobs: %d of %d raw", len(jobs), len(raw_all))

    jobs = dedupe(jobs)
    log.info("after cross-source de-dup: %d", len(jobs))

    for j in jobs:
        j.pop("benefit_snippets", None)  # used only during de-dup; the UI shows tags + amounts
        j["description"] = j["description"][:DESCRIPTION_CAP]
    # Always apply whatever is already in the cache (filled by the API pass or by
    # `python -m scraper.enrich_local` on a laptop); only call the API if a key is set.
    n_cached = llm_enrich.apply_cache(jobs, LLM_CACHE)
    log.info("applied cached LLM enrichment to %d jobs", n_cached)
    if not args.no_llm:
        llm_enrich.enrich(jobs, LLM_CACHE)

    merge_history(jobs)
    jobs.sort(key=lambda j: (j.get("posted_date") or "", j["title"]), reverse=True)

    DATA.mkdir(exist_ok=True)
    JOBS_PATH.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs}, separators=(",", ":"), ensure_ascii=False))
    META_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(jobs),
        "by_source": stats,
        "by_state": _count(jobs, lambda j: j["location"]["state"] or "??"),
        "by_type": _count(jobs, lambda j: j["job_type"]),
        "salary_disclosed": sum(1 for j in jobs if j["salary"]["disclosed"]),
        "effort_known": sum(1 for j in jobs if j["effort"]["clinical"] is not None),
        "llm_enriched": sum(1 for j in jobs if j.get("enriched_by") == "llm"),
    }, indent=1))
    log.info("wrote %s (%d jobs)", JOBS_PATH, len(jobs))
    return 0


def _count(jobs, keyfn):
    out: dict[str, int] = {}
    for j in jobs:
        k = keyfn(j)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    sys.exit(main())
