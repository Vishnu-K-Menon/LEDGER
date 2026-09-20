"""Polite HTTP for the listing and fetch stages (D-034 fetcher requirements): explicit UA,
robots.txt check per host, per-source request delay, exponential backoff on 429/5xx.
Every knob comes from ``fetch:`` in config; nothing numeric lives here."""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from ledger.config import FetchConfig

log = logging.getLogger(__name__)

GOVINFO_KEY_ENV = "GOVINFO_API_KEY"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class RobotsDisallowed(RuntimeError):
    pass


class Fetcher:
    """One session for the run. ``source`` selects the per-source delay."""

    def __init__(self, cfg: FetchConfig, *, sleep=time.sleep) -> None:
        self.cfg = cfg
        self._sleep = sleep
        self.session = requests.Session()
        self.session.headers["User-Agent"] = cfg.user_agent
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_call: dict[str, float] = {}
        self.calls = 0
        self.calls_by_host: dict[str, int] = {}

    # ---- robots -----------------------------------------------------------------------------

    def _robots_for(self, url: str) -> RobotFileParser | None:
        host = urlsplit(url).netloc
        if host not in self._robots:
            rp = RobotFileParser()
            robots_url = f"{urlsplit(url).scheme}://{host}/robots.txt"
            try:
                r = self.session.get(robots_url, timeout=self.cfg.timeout_s)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[host] = rp
                elif r.status_code in (401, 403):
                    # A host that 401/403s its own robots.txt (cbo.gov, gao.gov) is never fetched.
                    self._robots[host] = None
                    log.warning("%s: robots.txt returned %s -> never fetched", host, r.status_code)
                else:
                    # 404 (no robots.txt) or 5xx (api.govinfo.gov returns 500, 2026-09-20): no
                    # rules are available; a keyed API is meant to be called. Allow, and say so.
                    rp.parse([])
                    self._robots[host] = rp
                    if r.status_code != 404:
                        log.warning(
                            "%s: robots.txt returned %s -> no rules, allowing", host, r.status_code
                        )
            except requests.RequestException as exc:
                self._robots[host] = None
                log.warning("%s: robots.txt unreachable: %s -> never fetched", host, exc)
        return self._robots[host]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        if rp is None:
            return False
        return rp.can_fetch(self.cfg.user_agent, url)

    # ---- throttled, retried GET --------------------------------------------------------------

    def _throttle(self, source: str) -> None:
        delay = self.cfg.request_delay_s.get(source, 0.0)
        last = self._last_call.get(source)
        if last is not None:
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_call[source] = time.monotonic()

    def get(
        self, url: str, *, source: str, params: dict[str, Any] | None = None, stream: bool = False
    ) -> requests.Response:
        if not self.allowed(url):
            raise RobotsDisallowed(f"{url}: disallowed by robots.txt (or robots.txt unreachable)")
        backoff = self.cfg.backoff_base_s
        for attempt in range(self.cfg.max_retries + 1):
            self._throttle(source)
            self.calls += 1
            host = urlsplit(url).netloc
            self.calls_by_host[host] = self.calls_by_host.get(host, 0) + 1
            r = self.session.get(url, params=params, timeout=self.cfg.timeout_s, stream=stream)
            if r.status_code not in RETRY_STATUSES or attempt == self.cfg.max_retries:
                r.raise_for_status()
                return r
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
            wait = min(wait, self.cfg.backoff_max_s)
            log.warning(
                "%s -> %s; backing off %.1fs (attempt %d)", url, r.status_code, wait, attempt
            )
            self._sleep(wait)
            backoff = min(backoff * 2, self.cfg.backoff_max_s)
        raise AssertionError("unreachable")

    def get_json(self, url: str, *, source: str, params: dict[str, Any] | None = None) -> Any:
        return self.get(url, source=source, params=params).json()

    def get_text(self, url: str, *, source: str, params: dict[str, Any] | None = None) -> str:
        return self.get(url, source=source, params=params).text

    def download(
        self, url: str, dest, *, source: str, params: dict[str, Any] | None = None
    ) -> None:
        """Stream a file to ``dest`` (a Path). Caller decides whether to re-download."""
        r = self.get(url, source=source, params=params, stream=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)


def govinfo_api_key() -> str:
    """Production code reads the key from the environment only (CLAUDE.md, D-034)."""
    key = os.environ.get(GOVINFO_KEY_ENV, "")
    if not key:
        raise RuntimeError(
            f"{GOVINFO_KEY_ENV} is not set: GovInfo needs an api.data.gov key (D-034). "
            "Set it in the environment; DEMO_KEY rate-limits within a few calls."
        )
    return key
