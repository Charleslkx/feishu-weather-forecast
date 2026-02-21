#!/usr/bin/env python3
"""Webhook sender with retry and error normalization."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def post_webhook(
    *,
    url: str,
    payload: Dict[str, Any],
    timeout_seconds: int,
    max_retries: int,
    retry_backoff_seconds: float,
) -> Dict[str, Any]:
    if not url:
        return {"ok": False, "status": None, "error": "missing webhook url"}

    retries = max(0, int(max_retries))
    attempts = retries + 1
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    last_error = ""
    last_status: Optional[int] = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds))) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {"ok": True, "status": resp.getcode(), "body": body, "attempt": attempt}
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            last_error = f"http {exc.code}: {detail}"
        except urllib.error.URLError as exc:
            last_error = f"network: {exc.reason}"
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)

        if attempt < attempts:
            time.sleep(max(0.0, retry_backoff_seconds) * attempt)

    return {"ok": False, "status": last_status, "error": last_error, "attempt": attempts}
