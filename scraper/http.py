"""Polite HTTP helpers shared by every source adapter.

One shared session, a browser-like User-Agent, simple retry with backoff, and a
small delay between requests so we never hammer a job board.
"""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 heme-onc-jobs/1.0"
)
DELAY_SECONDS = 0.6
TIMEOUT = 30

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
_last_request = 0.0


def _throttle() -> None:
    global _last_request
    wait = DELAY_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def get(url: str, *, retries: int = 3, **kwargs) -> requests.Response | None:
    """GET with throttle + retry. Returns None (and logs) on persistent failure."""
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, timeout=TIMEOUT, **kwargs)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} for {url}")
            return r
        except Exception as e:  # noqa: BLE001
            log.warning("GET %s failed (attempt %d/%d): %s", url, attempt + 1, retries, e)
            time.sleep(2 ** attempt)
    return None


def post_json(url: str, body: dict, *, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.post(
                url,
                json=body,
                timeout=TIMEOUT,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            if r.status_code >= 400:
                raise requests.HTTPError(f"{r.status_code} for {url}")
            return r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("POST %s failed (attempt %d/%d): %s", url, attempt + 1, retries, e)
            time.sleep(2 ** attempt)
    return None


def get_json(url: str, **kwargs) -> dict | None:
    r = get(url, headers={"Accept": "application/json"}, **kwargs)
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        log.warning("Non-JSON response from %s", url)
        return None
