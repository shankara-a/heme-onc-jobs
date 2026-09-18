# Heme/Onc Jobs

A static GitHub Pages site that aggregates **hematology-oncology physician job postings across the US** and extracts, for each posting:

- **Salary** (posted base range, hourly/daily rates annualized)
- **Job type** — academic / community / industry / government (VA) / locums
- **MD/DO requirement**
- **Clinical vs. research vs. admin/teaching time split** when the posting states it
- **Benefits** — sign-on bonus, relocation, loan repayment, CME, malpractice/tail, retirement, PTO, partnership track, wRVU bonus, visa sponsorship, research start-up…
- Subspecialty tags, rank, posting/closing dates, and links back to the original listing(s)

The site defaults to **California** (its pay-transparency law means most CA postings carry a salary range) but every state is one dropdown away.

## How it works

```
GitHub Action (daily)  ──►  python -m scraper.run  ──►  data/jobs.json  ──►  index.html (GitHub Pages)
```

| Piece | What it does |
|---|---|
| `scraper/sources/madgex.py` | Madgex boards: ASCO Career Center, NEJM CareerCenter, Inside Higher Ed Careers, Nature Careers, Science Careers (RSS search → detail page JSON-LD) |
| `scraper/sources/ash.py` | ASH Job Center (full RSS feed + detail metadata) |
| `scraper/sources/practicematch.py` | PracticeMatch hematology-oncology listings (~650 nationally; JSON-LD detail pages) |
| `scraper/sources/workday.py` | Workday career sites: Amgen, Gilead/Kite, Roche/Genentech, BMS, Pfizer, Merck, AstraZeneca, Novartis, Sanofi, GSK, Sharp HealthCare (add more in `TENANTS`) |
| `scraper/sources/greenhouse.py` | Greenhouse boards for oncology biotech/diagnostics (Natera, Revolution Medicines, Nurix, Summit, Kymera, Erasca… add tokens in `BOARDS`) |
| `scraper/sources/ucrecruit.py` | UC academic recruitments (UCSF, UCLA, UCSD, UC Davis, UC Irvine) — salary ranges required by CA law |
| `scraper/sources/stanford.py` | Stanford Faculty Positions (facultypositions.stanford.edu) |
| `scraper/extract.py` | Rule-based extraction: relevance, job type, MD requirement, salary, effort split, benefits, subspecialties |
| `scraper/llm_enrich.py` | Optional Claude pass for the free-text fields (only runs if `ANTHROPIC_API_KEY` is set; cached per posting) |
| `scraper/run.py` | Orchestrates sources → normalize → de-dupe cross-listings → `data/jobs.json` + `data/meta.json` |
| `index.html`, `assets/` | Static UI: filters, job cards, Leaflet map, Chart.js insights, CSV export |

## Run locally

```bash
pip install -r requirements.txt
python -m scraper.run                # full scrape (~35 min, polite 0.6 s delay between requests)
python -m scraper.run --sources ash ucrecruit --no-llm   # quick subset
python3 -m http.server 8792          # then open http://localhost:8792
```

`fetch()` needs HTTP, so open the site through a local server rather than `file://`.

## Deploy to GitHub Pages

1. Create a **public** repo (e.g. `heme-onc-jobs`) and push this folder to `main`.
2. **Settings → Pages** → Source: *Deploy from a branch* → `main` / `/ (root)`. The `.nojekyll` file is already there.
3. **Settings → Actions → General → Workflow permissions** → *Read and write permissions* (so the daily Action can commit `data/jobs.json`).
4. **Actions → Refresh job data → Run workflow** to do the first scrape from CI (or commit the `data/` folder from a local run).
5. *(Optional)* Claude enrichment — reads each posting for the clinical/research split, benefits, call schedule and a summary. Two ways to run it:
   - **On your laptop with a Claude subscription (free):** install Claude Code (`curl -fsSL https://claude.ai/install.sh | bash`, then `claude auth login`) and run `python -m scraper.enrich_local` (add `--state CA` or `--limit 40` to start small). Results land in `data/llm_cache.json`; commit it and the Action applies them automatically. Re-run whenever you want new postings enriched — it only processes what's missing (~30 postings/min on Sonnet).
   - **Automatically in CI (pay-as-you-go API):** add a repo secret `ANTHROPIC_API_KEY`. With the cache pre-filled from the laptop backfill, the daily run only pays for new postings — cents per day on Sonnet 5 (`HOJ_LLM_MODEL` overrides the model).

The site will be at `https://<user>.github.io/heme-onc-jobs/`.

## Adding sources

- **Another Workday employer** (Genentech, City of Hope, Cedars-Sinai…): open any job on their careers site, read `https://{host}/{site}/job/...`, and append `{"key", "name", "host", "tenant", "site"}` to `TENANTS` in `scraper/sources/workday.py`. Test with `python -m scraper.run --sources workday --no-llm`.
- **Another Madgex board** (many specialty societies use it — look for `/jobsrss/` on the site): add to `BOARDS` in `madgex.py`.
- **Another Greenhouse company**: the token is the last path segment of `boards.greenhouse.io/{token}`; append `(token, "Name")` to `BOARDS` in `greenhouse.py`. Lever boards (`api.lever.co/v0/postings/{company}`) would follow the same pattern.
- **Another UC-style portal**: add to `CAMPUSES` in `ucrecruit.py`.
- Anything else: write a `fetch()` returning the raw-job dict shape used by the existing adapters and register it in `SOURCES` in `run.py`.

Boards that block scrapers or need a login (Indeed, LinkedIn, Doximity, PracticeLink search, DocCafe, MDLinx, PhysicianJobBoard, ACP, JAMA Career Center) are intentionally not included. USAJobs (VA positions) has a free API but requires registering for a key — a natural next addition.

## Caveats

All fields are extracted heuristically from free text. Salary ranges for open-rank academic pools (e.g. "Assistant to Full Professor") are wide by construction; "$300,000 or above" style brackets appear as a minimum only. Always verify on the original posting.
