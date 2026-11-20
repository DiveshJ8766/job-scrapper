"""Polite HTTP client: identifies itself, spaces requests, retries transient failures."""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceError(RuntimeError):
    """A source could not be fetched. Raised per source; the pipeline continues."""


class PoliteClient:
    def __init__(self, user_agent: str, timeout: float = 30.0, min_interval: float = 1.0,
                 max_retries: int = 3):
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request = 0.0

    def _wait_turn(self, min_interval: float | None) -> None:
        gap = self.min_interval if min_interval is None else min_interval
        elapsed = time.monotonic() - self._last_request
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request = time.monotonic()

    def get_json(self, url: str, *, params: dict | None = None,
                 min_interval: float | None = None):
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_turn(min_interval)
            try:
                resp = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                last_exc = exc
                log.warning("GET %s failed (attempt %d): %s", url, attempt, exc)
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise SourceError(f"{url}: response was not JSON") from exc
                if resp.status_code == 404:
                    raise SourceError(f"{url}: 404 Not Found (board or endpoint does not exist)")
                if resp.status_code not in RETRY_STATUS:
                    raise SourceError(f"{url}: HTTP {resp.status_code}: {resp.text[:200]}")
                last_exc = SourceError(f"{url}: HTTP {resp.status_code}")
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(min(int(retry_after), 60))
            time.sleep(2 ** attempt)
        raise SourceError(f"{url}: gave up after {self.max_retries} attempts: {last_exc}")

    def close(self) -> None:
        self._client.close()
