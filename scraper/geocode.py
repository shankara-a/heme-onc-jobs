"""Coordinates for cities not in geo.CITY_COORDS, via OpenStreetMap Nominatim.

Usage policy: at most 1 request/second, identify yourself, cache results.
Lookups are cached in data/geocode_cache.json (committed), so a daily run only
geocodes cities it has never seen. Also writes data/cities.json, the list the
site's "Near <city>" search autocompletes from.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from . import geo

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "heme-onc-jobs/1.0 (github.com/shankara-a/heme-onc-jobs)"}
MAX_LOOKUPS_PER_RUN = int(__import__("os").environ.get("HOJ_GEOCODE_MAX", "150"))


def _key(city: str, state: str) -> str:
    return f"{city.strip().lower()}|{state}"


def geocode_jobs(jobs: list[dict], cache_path: Path, cities_path: Path) -> int:
    cache: dict = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except ValueError:
            pass
    looked_up = 0
    placed = 0
    for j in jobs:
        loc = j.get("location") or {}
        city, state = loc.get("city"), loc.get("state")
        if not city or not state or loc.get("geo_precision") == "city":
            continue
        k = _key(city, state)
        if k not in cache:
            if looked_up >= MAX_LOOKUPS_PER_RUN:
                continue
            cache[k] = _lookup(city, state)
            looked_up += 1
            time.sleep(1.1)
        ll = cache.get(k)
        if ll:
            loc["lat"], loc["lon"], loc["geo_precision"] = ll[0], ll[1], "city"
            placed += 1
    if looked_up:
        cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True))
        log.info("geocoded %d new cities (%d misses)", looked_up, sum(1 for v in cache.values() if v is None))

    # City list for the site's "Near" autocomplete: built-in table + geocoded + whatever appears in jobs.
    cities: dict[str, list[float]] = {}
    for (c, s), (lat, lon) in geo.CITY_COORDS.items():
        cities[f"{c.title()}, {s}"] = [lat, lon]
    for k, v in cache.items():
        if v:
            c, s = k.split("|")
            cities.setdefault(f"{c.title()}, {s}", [v[0], v[1]])
    cities_path.write_text(json.dumps(dict(sorted(cities.items())), separators=(",", ":")))
    return placed


def _lookup(city: str, state: str) -> list[float] | None:
    try:
        r = requests.get(NOMINATIM, params={"q": f"{city}, {geo.STATES.get(state, state)}, USA", "format": "json",
                                            "limit": 1, "countrycodes": "us"}, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            log.warning("nominatim %s for %s, %s", r.status_code, city, state)
            return None
        hits = r.json()
        if not hits:
            return None
        return [round(float(hits[0]["lat"]), 4), round(float(hits[0]["lon"]), 4)]
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("nominatim failed for %s, %s: %s", city, state, e)
        return None
