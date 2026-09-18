"""Backfill LLM enrichment on a laptop using Claude Code (covered by a Claude
subscription) instead of the pay-as-you-go API.

    python -m scraper.enrich_local                 # every posting not yet in the cache
    python -m scraper.enrich_local --state CA      # one state first
    python -m scraper.enrich_local --limit 40      # smoke test
    python -m scraper.enrich_local --model opus    # default: sonnet

Each call hands ~8 postings to `claude -p --json-schema ...` and stores the
answers in data/llm_cache.json under the same keys `llm_enrich.py` uses, so the
daily GitHub Action (which runs `python -m scraper.run`) applies them without
any API key. Re-run `python -m scraper.run --raw-cache ...` or just re-run the
Action to fold the new fields into data/jobs.json; this script also applies
them to the current data/jobs.json immediately.

Resumable: the cache is written after every batch, so Ctrl-C or a rate-limit
pause loses at most one batch.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import llm_enrich

ROOT = Path(__file__).resolve().parent.parent
JOBS_PATH = ROOT / "data" / "jobs.json"
CACHE_PATH = ROOT / "data" / "llm_cache.json"
log = logging.getLogger("enrich_local")

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, **llm_enrich.SCHEMA["properties"]},
                "required": ["index", *llm_enrich.SCHEMA["required"]],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    llm_enrich.SYSTEM
    + " You are given several postings, each headed by '=== POSTING <index> ==='. "
    "Return one result object per posting with its index. Do not use any tools; just read and answer."
)
PROMPT_HEAD = ""


def find_claude() -> str:
    for cand in [os.environ.get("CLAUDE_BIN"), shutil.which("claude"), Path.home() / ".local/bin/claude"]:
        if cand and Path(cand).exists():
            return str(cand)
    sys.exit("claude CLI not found. Install: curl -fsSL https://claude.ai/install.sh | bash  (then run `claude` once to sign in)")


def run_batch(claude: str, model: str, batch: list[dict], timeout: int = 600) -> dict[str, dict]:
    prompt = PROMPT_HEAD + "".join(
        f"\n=== POSTING {i} ===\n{llm_enrich.build_blob(j)}\n" for i, j in enumerate(batch)
    )
    # Keep each call lean: no MCP servers, plugins, or tools (those add ~160k tokens
    # of context per call on a typical desktop setup), and our own system prompt
    # instead of Claude Code's coding-agent one. Measured overhead: ~1.3k tokens.
    cmd = [
        claude, "-p", "--no-session-persistence",
        "--model", model, "--effort", "low",
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--setting-sources", "",
        "--output-format", "json",
        "--json-schema", json.dumps(BATCH_SCHEMA),
    ]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    out = json.loads(proc.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude error: {str(out.get('result'))[:300]}")
    data = out.get("structured_output")
    if data is None:  # older CLI versions put the JSON text in `result`
        data = json.loads(out.get("result") or "{}")
    results = {}
    for r in data.get("results", []):
        idx = r.pop("index", None)
        if isinstance(idx, int) and 0 <= idx < len(batch):
            results[llm_enrich.cache_key(batch[idx])] = r
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="two-letter state code, e.g. CA")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--dry-run", action="store_true", help="only report how many postings need enrichment")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", stream=sys.stderr)

    data = json.loads(JOBS_PATH.read_text())
    jobs = data["jobs"]
    cache = llm_enrich.load_cache(CACHE_PATH)
    todo = [j for j in jobs if llm_enrich.cache_key(j) not in cache]
    if args.state:
        todo = [j for j in todo if (j.get("location") or {}).get("state") == args.state.upper()]
    if args.limit:
        todo = todo[: args.limit]
    log.info("%d postings total, %d already cached, %d to enrich", len(jobs), len(jobs) - len([j for j in jobs if llm_enrich.cache_key(j) not in cache]), len(todo))
    if args.dry_run or not todo:
        return 0

    claude = find_claude()
    done, t0 = 0, time.time()
    for i in range(0, len(todo), args.batch_size):
        batch = todo[i: i + args.batch_size]
        for attempt in range(3):
            try:
                results = run_batch(claude, args.model, batch)
                break
            except (RuntimeError, subprocess.TimeoutExpired, ValueError) as e:
                wait = 30 * (attempt + 1)
                log.warning("batch %d failed (%s); retrying in %ds", i // args.batch_size, str(e)[:200], wait)
                time.sleep(wait)
        else:
            log.error("giving up on batch starting at %d; cache so far is saved", i)
            continue
        cache.update(results)
        CACHE_PATH.write_text(json.dumps(cache))
        done += len(results)
        rate = done / max(1, time.time() - t0) * 60
        log.info("%d/%d enriched (%.0f/min, %d missing in this batch)", done, len(todo), rate, len(batch) - len(results))
        time.sleep(1)  # be gentle with the subscription rate limiter

    n = llm_enrich.apply_cache(jobs, CACHE_PATH)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    JOBS_PATH.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    log.info("applied enrichment to %d of %d jobs in %s", n, len(jobs), JOBS_PATH.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
