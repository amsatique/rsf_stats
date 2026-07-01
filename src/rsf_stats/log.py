"""Centralised logging: one logger, a consistent format, and an httpx hook.

Every outgoing request to rallysimfans.hu is logged (method, URL, status, timing,
size) at DEBUG, so a single `RSF_LOG_LEVEL=DEBUG` makes the server interaction
fully traceable. Key application events (login, cache, cooldown, ranks) log at INFO.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("rsf_stats")

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure the `rsf_stats` logger once with a readable format."""
    global _CONFIGURED
    if _CONFIGURED:
        logger.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    _CONFIGURED = True


def log_response(response: httpx.Response) -> None:
    """httpx response event hook: trace each server round-trip."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    req = response.request
    try:
        ms = response.elapsed.total_seconds() * 1000
    except RuntimeError:  # elapsed not available yet (streaming)
        ms = 0.0
    size = response.headers.get("content-length", "?")
    logger.debug("%s %s → %s (%.0f ms, %s B)", req.method, req.url, response.status_code, ms, size)
