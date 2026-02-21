#!/usr/bin/env python3
"""Unified forecast entrypoint: OpenWeather (D+1~D+3) + Open-Meteo (D+4~D+7)."""

from __future__ import annotations

import argparse
import json

try:
    from scripts.services.fusion_service import get_fused_forecast
except ImportError:
    from services.fusion_service import get_fused_forecast


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fused weather forecast (OpenWeather + Open-Meteo)")
    parser.add_argument("--region", help="Region name, e.g. Beijing or 'Guiyang, Guizhou'")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD, within D+1~D+7")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD, within D+1~D+7")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="Timezone for Open-Meteo output")
    parser.add_argument("--include-holiday", action="store_true", help="Attach holiday labels when available")
    parser.add_argument("--json-only", action="store_true", help="Print JSON only")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    result = get_fused_forecast(
        region=args.region,
        lat=args.lat,
        lon=args.lon,
        start_date=args.start_date,
        end_date=args.end_date,
        timezone=args.timezone,
        include_holiday=args.include_holiday,
    )

    if not args.json_only:
        print(result.get("summary_en", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    has_data = bool(
        result.get("forecast_short_open_weather", {}).get("days")
        or result.get("forecast_long_open_meteo", {}).get("days")
    )
    return 0 if has_data else 1


if __name__ == "__main__":
    raise SystemExit(main())
