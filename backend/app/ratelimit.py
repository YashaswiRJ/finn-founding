"""A small in-process rate limit for endpoints that can reach a paid model (Ask, network questions).

Single-process app, so a dict of token buckets is enough; a multi-instance deployment would move this
to the gateway or Redis.
"""
import threading
import time

from fastapi import HTTPException, Request

PER_MINUTE = 30
_buckets: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()


def limit(request: Request) -> None:
    key = (request.client.host if request.client else "unknown") + request.url.path
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(key, (float(PER_MINUTE), now))
        tokens = min(float(PER_MINUTE), tokens + (now - last) * PER_MINUTE / 60.0)
        if tokens < 1:
            raise HTTPException(429, "Too many questions in a minute. Try again shortly.")
        _buckets[key] = (tokens - 1, now)
