#!/usr/bin/env python3
"""Fusion logic for configurable Open-Meteo/OpenWeather forecast composition."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from scripts.providers.open_meteo_client import OpenMeteoProviderError, fetch_long_forecast, load_config
    from scripts.providers.open_weather_client import OpenWeatherProviderError, fetch_short_forecast, resolve_location
    from scripts.services.output_compact import build_summary_en, compact_open_meteo_hourly_to_daily
except ImportError:
    from providers.open_meteo_client import OpenMeteoProviderError, fetch_long_forecast, load_config
    from providers.open_weather_client import OpenWeatherProviderError, fetch_short_forecast, resolve_location
    from services.output_compact import build_summary_en, compact_open_meteo_hourly_to_daily

UTC8 = timezone(timedelta(hours=8))
WEEKDAY_LABELS_UTC8 = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEATHER_MODE_OPEN_METEO_ALL = "open_meteo_all"
WEATHER_MODE_HYBRID = "hybrid"


def _parse_date(text: str, field_name: str) -> date:
    try:
        return date.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _date_window(start_date: Optional[str], end_date: Optional[str]) -> Tuple[date, date, date, date, date, date]:
    today = datetime.now(UTC8).date()
    d1 = today + timedelta(days=1)
    d3 = today + timedelta(days=3)
    d4 = today + timedelta(days=4)
    d7 = today + timedelta(days=7)

    if start_date is None and end_date is None:
        start = d1
        end = d7
    elif start_date is not None and end_date is not None:
        start = _parse_date(start_date, "start_date")
        end = _parse_date(end_date, "end_date")
    else:
        raise ValueError("start_date and end_date must be provided together")

    if start > end:
        raise ValueError("start_date cannot be after end_date")
    if start < d1 or end > d7:
        raise ValueError("date range must be within D+1 to D+7 (UTC+8)")

    return start, end, d1, d3, d4, d7


def _intersect(a_start: date, a_end: date, b_start: date, b_end: date) -> Optional[Tuple[date, date]]:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return None
    return start, end


def _weekday_utc8(date_text: str) -> Optional[str]:
    try:
        day = date.fromisoformat(date_text)
    except Exception:
        return None
    return WEEKDAY_LABELS_UTC8[day.weekday()]


def _attach_calendar_info(days: List[Dict[str, Any]], include_holiday: bool = False) -> None:
    get_holiday_info = None
    download_ics = None
    save_cache = None
    parse_ics = None

    if include_holiday:
        try:
            try:
                from scripts.holiday_fetch import (
                    get_holiday_info as _holiday_lookup,  # type: ignore
                    download_ics as _download_ics,  # type: ignore
                    save_cache as _save_cache,  # type: ignore
                    parse_ics as _parse_ics,  # type: ignore
                )
            except ImportError:
                from holiday_fetch import (
                    get_holiday_info as _holiday_lookup,  # type: ignore
                    download_ics as _download_ics,  # type: ignore
                    save_cache as _save_cache,  # type: ignore
                    parse_ics as _parse_ics,  # type: ignore
                )
            get_holiday_info = _holiday_lookup
            download_ics = _download_ics
            save_cache = _save_cache
            parse_ics = _parse_ics
        except Exception:
            get_holiday_info = None
            download_ics = None
            save_cache = None
            parse_ics = None

        # Auto-download holidays if cache is missing and functions are available
        if get_holiday_info is not None and download_ics is not None:
            try:
                from scripts.holiday_fetch import _get_cache_file as get_cache_file_path  # type: ignore
            except ImportError:
                try:
                    from holiday_fetch import _get_cache_file as get_cache_file_path  # type: ignore
                except ImportError:
                    get_cache_file_path = None

            if get_cache_file_path is not None:
                cache_file = get_cache_file_path().expanduser()
                cache_ready = False
                try:
                    cache_ready = cache_file.exists() and cache_file.stat().st_size > 0
                except OSError:
                    cache_ready = False

                if not cache_ready and download_ics is not None and save_cache is not None and parse_ics is not None:
                    ics_content = download_ics()
                    if ics_content:
                        events = parse_ics(ics_content)
                        save_cache(events)

                # Ensure cache file exists to avoid repeated "missing file" state.
                if not cache_file.exists():
                    try:
                        cache_file.parent.mkdir(parents=True, exist_ok=True)
                        cache_file.touch()
                    except OSError:
                        pass

    for item in days:
        date_text = item.get("date")
        if not date_text:
            continue

        weekday = _weekday_utc8(date_text)
        if weekday:
            item["weekday_utc8"] = weekday

        if not include_holiday or get_holiday_info is None:
            continue
        holiday = get_holiday_info(date_text)
        if holiday:
            item["holiday"] = holiday


def _get_weather_source_mode() -> str:
    try:
        config = load_config()
    except Exception:
        config = {}

    providers = config.get("providers") if isinstance(config, dict) else {}
    if not isinstance(providers, dict):
        providers = {}

    env_mode = os.getenv("WEATHER_SOURCE_MODE", "").strip().lower()
    mode = env_mode or str(providers.get("weather_source_mode", WEATHER_MODE_OPEN_METEO_ALL)).strip().lower()
    return mode if mode in {WEATHER_MODE_OPEN_METEO_ALL, WEATHER_MODE_HYBRID} else WEATHER_MODE_OPEN_METEO_ALL


def _filter_days_by_range(days: List[Dict[str, Any]], date_range: Optional[Tuple[date, date]]) -> List[Dict[str, Any]]:
    if not date_range:
        return []

    start, end = date_range
    filtered: List[Dict[str, Any]] = []
    for item in days:
        text = item.get("date")
        if not text:
            continue
        try:
            value = date.fromisoformat(text)
        except Exception:
            continue
        if start <= value <= end:
            filtered.append(item)
    return filtered


def _fetch_open_meteo_days(
    *, lat: float, lon: float, start_date: date, end_date: date, timezone: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    raw_result = fetch_long_forecast(
        lat=lat,
        lon=lon,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )
    compact = compact_open_meteo_hourly_to_daily(
        raw_result.get("raw") or {},
        key_hours=(raw_result.get("config") or {}).get("key_hours") or [9, 15, 21],
        rounding=(raw_result.get("config") or {}).get("rounding") or {},
    )
    return compact.get("days") or [], compact.get("units") or {}, raw_result.get("source_call") or {}


def get_fused_forecast(
    region: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = "Asia/Shanghai",
    include_holiday: bool = False,
) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    source_calls: List[Dict[str, Any]] = []
    short_days: List[Dict[str, Any]] = []
    long_days: List[Dict[str, Any]] = []
    location: Dict[str, Any] = {}
    weather_source_mode = _get_weather_source_mode()
    short_source = "open_weather" if weather_source_mode == WEATHER_MODE_HYBRID else "open_meteo"

    try:
        start, end, d1, d3, d4, d7 = _date_window(start_date, end_date)
    except ValueError as exc:
        return {
            "query": {
                "region": region,
                "lat": lat,
                "lon": lon,
                "start_date": start_date,
                "end_date": end_date,
                "timezone": timezone,
                "include_holiday": include_holiday,
            },
            "location": {},
            "time_window": {},
            "split_strategy": {"short_source": short_source, "long_source": "open_meteo"},
            "forecast_short_open_weather": {"days": []},
            "forecast_long_open_meteo": {"days": []},
            "summary_en": "",
            "errors": [{"source": "fusion", "code": "INVALID_TIME_RANGE", "message": str(exc), "details": {}}],
            "meta": {"generated_at_utc8": datetime.now(UTC8).isoformat(), "source_calls": []},
        }

    short_range = _intersect(start, end, d1, d3)
    long_range = _intersect(start, end, d4, d7)

    try:
        resolved = resolve_location(region=region, lat=lat, lon=lon)
        location = resolved["location"]
        source_calls.extend(resolved.get("source_calls") or [])
    except OpenWeatherProviderError as exc:
        errors.append({"source": "open_weather", "code": exc.code, "message": exc.message, "details": exc.details})

    long_units: Dict[str, Any] = {}
    if location:
        if weather_source_mode == WEATHER_MODE_HYBRID and short_range:
            try:
                short = fetch_short_forecast(
                    lat=location["lat"],
                    lon=location["lon"],
                    start_date=short_range[0],
                    end_date=short_range[1],
                )
                short_days = short.get("days") or []
                source_calls.extend(short.get("source_calls") or [])
            except OpenWeatherProviderError as exc:
                errors.append({"source": "open_weather", "code": exc.code, "message": exc.message, "details": exc.details})

        if weather_source_mode == WEATHER_MODE_HYBRID:
            if long_range:
                try:
                    long_days, long_units, source_call = _fetch_open_meteo_days(
                        lat=float(location["lat"]),
                        lon=float(location["lon"]),
                        start_date=long_range[0],
                        end_date=long_range[1],
                        timezone=timezone,
                    )
                    source_calls.append(source_call)
                except OpenMeteoProviderError as exc:
                    errors.append({"source": "open_meteo", "code": exc.code, "message": exc.message, "details": exc.details})
        else:
            try:
                all_days, long_units, source_call = _fetch_open_meteo_days(
                    lat=float(location["lat"]),
                    lon=float(location["lon"]),
                    start_date=start,
                    end_date=end,
                    timezone=timezone,
                )
                source_calls.append(source_call)
                short_days = _filter_days_by_range(all_days, short_range)
                long_days = _filter_days_by_range(all_days, long_range)
            except OpenMeteoProviderError as exc:
                errors.append({"source": "open_meteo", "code": exc.code, "message": exc.message, "details": exc.details})

    _attach_calendar_info(short_days, include_holiday=include_holiday)
    _attach_calendar_info(long_days, include_holiday=include_holiday)

    location_text = (
        location.get("resolved_location")
        or location.get("input_region")
        or (f"{location.get('lat')}, {location.get('lon')}" if location else "target location")
    )

    summary = build_summary_en(location_text, short_days, long_days)

    if errors and (short_days or long_days):
        errors.append(
            {
                "source": "fusion",
                "code": "PARTIAL_DATA",
                "message": "One upstream provider failed, partial data returned",
                "details": {},
            }
        )

    short_units = {
        "temperature": "celsius",
        "precipitation": "mm",
        "wind_speed": "m/s",
        "humidity": "%",
    }
    if short_source == "open_meteo" and long_units:
        short_units = long_units

    return {
        "query": {
            "region": region,
            "lat": lat,
            "lon": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": timezone,
            "include_holiday": include_holiday,
            "weather_source_mode": weather_source_mode,
        },
        "location": location,
        "time_window": {
            "timezone": "UTC+08:00",
            "request_start": start.isoformat(),
            "request_end": end.isoformat(),
        },
        "split_strategy": {
            "short_source": short_source,
            "long_source": "open_meteo",
            "short_range":
                {"start": short_range[0].isoformat(), "end": short_range[1].isoformat()} if short_range else None,
            "long_range":
                {"start": long_range[0].isoformat(), "end": long_range[1].isoformat()} if long_range else None,
        },
        "forecast_short_open_weather": {
            "days": short_days,
            "units": short_units,
        },
        "forecast_long_open_meteo": {"days": long_days, "units": long_units},
        "summary_en": summary,
        "errors": errors,
        "meta": {
            "generated_at_utc8": datetime.now(UTC8).isoformat(),
            "source_calls": source_calls,
        },
    }
