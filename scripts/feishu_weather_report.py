#!/usr/bin/env python3
"""Generate and push fixed-format weather reports to Feishu webhook trigger."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

try:
    from scripts.providers.open_meteo_client import load_config
    from scripts.services.feishu_report_builder import build_payload_from_forecast, weather_to_cn_icon
    from scripts.services.fusion_service import get_fused_forecast
    from scripts.services.webhook_sender import post_webhook
except ImportError:
    from providers.open_meteo_client import load_config
    from services.feishu_report_builder import build_payload_from_forecast, weather_to_cn_icon
    from services.fusion_service import get_fused_forecast
    from services.webhook_sender import post_webhook

UTC8 = timezone(timedelta(hours=8))
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "fusion_config.yaml"


def _build_runtime_config(config_path: str) -> Dict[str, Any]:
    os.environ["FUSION_CONFIG_FILE"] = config_path
    config = load_config(config_path=config_path)
    report = config.get("report") if isinstance(config, dict) else {}
    if not isinstance(report, dict):
        report = {}
    webhook = report.get("webhook") if isinstance(report.get("webhook"), dict) else {}
    defaults = report.get("defaults") if isinstance(report.get("defaults"), dict) else {}

    city = os.getenv("WEATHER_REPORT_CITY", "").strip() or str(report.get("city") or "Shanghai")
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip() or str(webhook.get("url") or "")

    mode_default = str(defaults.get("weather_source_mode") or "").strip().lower()
    if mode_default and not os.getenv("WEATHER_SOURCE_MODE", "").strip():
        os.environ["WEATHER_SOURCE_MODE"] = mode_default

    return {
        "city": city,
        "timezone": str(report.get("timezone") or "Asia/Shanghai"),
        "include_holiday": bool(report.get("include_holiday", True)),
        "source_cn": str(report.get("source_cn") or "OpenWeather + Open-Meteo"),
        "updated_at_format": str(report.get("updated_at_format") or "%Y-%m-%d %H:%M:%S"),
        "webhook_url": webhook_url,
        "webhook_timeout_seconds": int(webhook.get("timeout_seconds", 10)),
        "webhook_max_retries": int(webhook.get("max_retries", 2)),
        "webhook_retry_backoff_seconds": float(webhook.get("retry_backoff_seconds", 1.5)),
    }


def _now_in_timezone(tz_name: str) -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now(UTC8)


def run_once(runtime_config: Dict[str, Any], *, dry_run: bool, json_debug: bool) -> bool:
    city = runtime_config["city"]
    timezone_name = runtime_config["timezone"]
    include_holiday = bool(runtime_config["include_holiday"])
    source_cn = runtime_config["source_cn"]

    forecast = get_fused_forecast(
        region=city,
        timezone=timezone_name,
        include_holiday=include_holiday,
    )

    short_days = (forecast.get("forecast_short_open_weather") or {}).get("days") or []
    long_days = (forecast.get("forecast_long_open_meteo") or {}).get("days") or []
    has_days = bool(short_days or long_days)
    if not has_days:
        print(json.dumps({"ok": False, "error": "no forecast days", "errors": forecast.get("errors") or []}, ensure_ascii=False))
        return False

    now_dt = _now_in_timezone(timezone_name)
    updated_at_cn = now_dt.strftime(runtime_config["updated_at_format"])
    payload = build_payload_from_forecast(
        forecast_result=forecast,
        city=city,
        source_cn=source_cn,
        updated_at_cn=updated_at_cn,
        include_holiday=include_holiday,
    )

    if json_debug:
        print(json.dumps({"forecast": forecast, "payload": payload}, ensure_ascii=False, indent=2))

    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return True

    send_result = post_webhook(
        url=runtime_config["webhook_url"],
        payload=payload,
        timeout_seconds=runtime_config["webhook_timeout_seconds"],
        max_retries=runtime_config["webhook_max_retries"],
        retry_backoff_seconds=runtime_config["webhook_retry_backoff_seconds"],
    )
    print(json.dumps(send_result, ensure_ascii=False))
    return bool(send_result.get("ok"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fixed-format Feishu weather report sender")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to fusion YAML config file (default: config/fusion_config.yaml)",
    )
    parser.add_argument("--once", action="store_true", help="Run once and send")
    parser.add_argument("--dry-run", action="store_true", help="Print webhook payload only")
    parser.add_argument("--json-debug", action="store_true", help="Print detailed forecast and payload json")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config_path = str(Path(args.config).expanduser())
    runtime_config = _build_runtime_config(config_path)

    ok = run_once(runtime_config, dry_run=args.dry_run, json_debug=args.json_debug)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
