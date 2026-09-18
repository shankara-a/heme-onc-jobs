"""Optional Claude-based enrichment.

Regex gets salary and benefits reasonably well, but "80% clinical / 20%
protected research" phrasing is too varied for rules. When ANTHROPIC_API_KEY is
set (locally or as a GitHub Actions secret) this module asks Claude for a
structured read of each *new* posting and overrides the rule-based fields.

Results are cached in data/llm_cache.json keyed by a hash of the posting text,
so a re-run only pays for postings that changed or are new.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

MODEL = os.environ.get("HOJ_LLM_MODEL", "claude-sonnet-5")
MAX_CHARS = 7000

SCHEMA = {
    "type": "object",
    "properties": {
        "job_type": {"type": "string", "enum": ["academic", "community", "industry", "government", "locums", "unknown"]},
        "md_required": {"type": "boolean"},
        "salary_min": {"type": ["integer", "null"], "description": "Annual USD base salary lower bound stated in the posting, else null"},
        "salary_max": {"type": ["integer", "null"]},
        "clinical_pct": {"type": ["integer", "null"], "description": "Percent of effort in clinical care if stated or clearly implied"},
        "research_pct": {"type": ["integer", "null"]},
        "admin_pct": {"type": ["integer", "null"]},
        "teaching_pct": {"type": ["integer", "null"]},
        "effort_note": {"type": ["string", "null"], "description": "Short quote describing the time split, or null"},
        "benefits": {"type": "array", "items": {"type": "string"}, "description": "Short benefit phrases actually stated (e.g. '$50k sign-on bonus', 'loan repayment', '6 weeks PTO')"},
        "subspecialties": {"type": "array", "items": {"type": "string"}},
        "call_schedule": {"type": ["string", "null"]},
        "summary": {"type": "string", "description": "One or two sentences a fellow would want to know"},
    },
    "required": ["job_type", "md_required", "salary_min", "salary_max", "clinical_pct", "research_pct",
                 "admin_pct", "teaching_pct", "effort_note", "benefits", "subspecialties", "call_schedule", "summary"],
    "additionalProperties": False,
}

SYSTEM = (
    "You extract structured facts from physician job postings in hematology/oncology. "
    "Only report what the posting states or clearly implies; use null when it is not stated. "
    "Salary must be annual base pay in USD (annualize hourly/daily rates; ignore bonuses). "
    "Job type: academic = university/medical school faculty; community = private practice, medical group or "
    "hospital-employed clinical role; industry = pharma/biotech/CRO; government = VA, NIH, military, IHS; "
    "locums = temporary coverage."
)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def build_blob(job: dict) -> str:
    """The exact text a model is asked to read; also the cache key material."""
    return (f"TITLE: {job['title']}\nEMPLOYER: {job.get('employer')}\nLOCATION: {job.get('location_text') or (job.get('location') or {}).get('text')}\n"
            f"SALARY FIELD: {(job.get('salary') or {}).get('text') if isinstance(job.get('salary'), dict) else job.get('salary_text')}\n\n"
            f"{job.get('description', '')[:MAX_CHARS]}")


def cache_key(job: dict) -> str:
    return _hash(build_blob(job))


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except ValueError:
            log.warning("unreadable %s, starting a fresh cache", cache_path)
    return {}


def apply_cache(jobs: list[dict], cache_path: Path) -> int:
    """Apply previously extracted fields (from the API or the local Claude Code
    backfill) without making any API calls. Returns number of jobs enriched."""
    cache = load_cache(cache_path)
    n = 0
    for job in jobs:
        parsed = cache.get(cache_key(job))
        if parsed:
            _apply(job, parsed)
            n += 1
    return n


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def enrich(jobs: list[dict], cache_path: Path) -> int:
    """Mutates jobs in place. Returns number of API calls made."""
    if not enabled():
        log.info("LLM enrichment skipped (no ANTHROPIC_API_KEY)")
        return 0
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic package not installed; skipping LLM enrichment")
        return 0

    cache = load_cache(cache_path)
    client = anthropic.Anthropic()
    calls = 0
    for job in jobs:
        blob = build_blob(job)
        key = _hash(blob)
        parsed = cache.get(key)
        if parsed is None:
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=2000,
                    system=SYSTEM,
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                    messages=[{"role": "user", "content": blob}],
                )
                text = next(b.text for b in resp.content if b.type == "text")
                parsed = json.loads(text)
                cache[key] = parsed
                calls += 1
                if calls % 25 == 0:
                    cache_path.write_text(json.dumps(cache))
            except anthropic.RateLimitError as e:
                log.warning("rate limited, stopping enrichment early: %s", e)
                break
            except anthropic.APIStatusError as e:
                log.warning("API error for %s: %s", job.get("source_url"), e)
                continue
            except (anthropic.APIConnectionError, ValueError, StopIteration) as e:
                log.warning("enrichment failed for %s: %s", job.get("source_url"), e)
                continue
        _apply(job, parsed)
    cache_path.write_text(json.dumps(cache))
    log.info("LLM enrichment: %d new calls, %d cached", calls, len(jobs) - calls)
    return calls


def _apply(job: dict, p: dict) -> None:
    job["enriched_by"] = "llm"
    if p.get("job_type") and p["job_type"] != "unknown":
        job["job_type"] = p["job_type"]
        job["job_type_confidence"] = 0.9
    job["md_required"] = p.get("md_required")
    if p.get("salary_min") or p.get("salary_max"):
        lo, hi = p.get("salary_min"), p.get("salary_max")
        if lo is None:
            lo = hi
        job["salary"] = {"min": lo, "max": hi, "period": "year", "disclosed": True,
                         "text": (job.get("salary") or {}).get("text") or "LLM-extracted", "annualized_from": None}
    eff = job.setdefault("effort", {})
    for k in ("clinical", "research", "admin", "teaching"):
        v = p.get(f"{k}_pct")
        if v is not None:
            eff[k] = v
    if p.get("effort_note"):
        eff["text"] = p["effort_note"]
    if p.get("benefits"):
        job["benefits_llm"] = p["benefits"]
    if p.get("subspecialties"):
        job["subspecialties_llm"] = p["subspecialties"]
    job["call_schedule"] = p.get("call_schedule")
    job["summary"] = p.get("summary")
