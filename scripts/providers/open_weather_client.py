#!/usr/bin/env python3
"""OpenWeather provider for location resolving and short-range forecasts."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from scripts.weather_query import _get_settings, _resolve_location, query_weather  # type: ignore
    from scripts.providers.open_meteo_client import load_config  # type: ignore
except ImportError:
    from weather_query import _get_settings, _resolve_location, query_weather  # type: ignore
    from providers.open_meteo_client import load_config  # type: ignore

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEOCODING_CACHE_FILE = SCRIPT_ROOT / ".cache" / "openweather_geocoding_cache.json"


class OpenWeatherProviderError(RuntimeError):
    """Provider-level wrapper for OpenWeather failures."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _extract_error(payload: Dict[str, Any]) -> OpenWeatherProviderError:
    errors = payload.get("errors") or []
    if not errors:
        return OpenWeatherProviderError("OPENWEATHER_UNKNOWN", "OpenWeather query failed")
    item = errors[0]
    return OpenWeatherProviderError(
        item.get("code", "OPENWEATHER_UNKNOWN"),
        item.get("message", "OpenWeather query failed"),
        item.get("details") or {},
    )


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_region_key(region: str) -> str:
    text = region.strip().lower().replace("，", ",")
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(", ").strip()


def _get_geocoding_cache_settings() -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    try:
        loaded = load_config()
        if isinstance(loaded, dict):
            config = loaded
    except Exception:
        config = {}

    cache_cfg = config.get("geocoding_cache") or {}
    if not isinstance(cache_cfg, dict):
        cache_cfg = {}

    enabled = bool(cache_cfg.get("enabled", True))
    env_enabled = os.getenv("OPENWEATHER_GEOCODING_CACHE_ENABLED", "").strip()
    if env_enabled:
        enabled = _truthy(env_enabled)

    raw_path = os.getenv("OPENWEATHER_GEOCODING_CACHE_FILE", "").strip() or str(cache_cfg.get("file") or "").strip()
    if raw_path:
        cache_file = Path(raw_path).expanduser()
        if not cache_file.is_absolute():
            cache_file = SCRIPT_ROOT / cache_file
    else:
        cache_file = DEFAULT_GEOCODING_CACHE_FILE

    return {"enabled": enabled, "file": cache_file}


def _load_geocoding_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_geocoding_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_lookup(region: str, source_calls: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    settings = _get_geocoding_cache_settings()
    if not settings["enabled"]:
        return None

    key = _normalize_region_key(region)
    if not key:
        return None

    cache_file: Path = settings["file"]
    cache = _load_geocoding_cache(cache_file)
    item = cache.get(key)
    if not isinstance(item, dict):
        return None

    lat = item.get("lat")
    lon = item.get("lon")
    if lat is None or lon is None:
        return None

    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except Exception:
        return None

    source_calls.append(
        {
            "endpoint": "openweather_geocoding_cache",
            "params": {"q": region},
            "cache_hit": True,
        }
    )
    return {
        "lat": lat_value,
        "lon": lon_value,
        "input_region": region,
        "resolved_location": item.get("resolved_location"),
        "source": "geocoding_cache",
    }


def _cache_store(region: str, location: Dict[str, Any], source_calls: List[Dict[str, Any]]) -> None:
    settings = _get_geocoding_cache_settings()
    if not settings["enabled"]:
        return

    key = _normalize_region_key(region)
    if not key:
        return

    cache_file: Path = settings["file"]
    cache = _load_geocoding_cache(cache_file)
    cache[key] = {
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "resolved_location": location.get("resolved_location"),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    try:
        _save_geocoding_cache(cache_file, cache)
        source_calls.append(
            {
                "endpoint": "openweather_geocoding_cache",
                "params": {"q": region},
                "cache_write": True,
            }
        )
    except Exception:
        return


def resolve_location(
    region: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve location using OpenWeather geocoding behavior in weather_query.py."""
    source_calls: List[Dict[str, Any]] = []

    if (lat is None) != (lon is None):
        raise OpenWeatherProviderError("MISSING_LOCATION", "lat and lon must be provided together")
    if lat is not None and lon is not None:
        return {
            "location": {
                "lat": float(lat),
                "lon": float(lon),
                "input_region": region,
                "resolved_location": None,
                "source": "latlon",
            },
            "source_calls": source_calls,
        }

    if not region or not str(region).strip():
        raise OpenWeatherProviderError("MISSING_LOCATION", "region or lat/lon is required")

    cached_location = _cache_lookup(region, source_calls)
    if cached_location is not None:
        return {
            "location": cached_location,
            "source_calls": source_calls,
        }

    api_key, timeout = _get_settings()
    if not api_key:
        raise OpenWeatherProviderError("MISSING_API_KEY", "OPENWEATHER_API_KEY is not configured")
    try:
        location = _resolve_location(region, lat, lon, api_key, timeout, source_calls)
    except Exception as exc:  # weather_query internal exception type
        code = getattr(exc, "code", "LOCATION_RESOLVE_FAILED")
        message = getattr(exc, "message", str(exc))
        details = getattr(exc, "details", {})
        raise OpenWeatherProviderError(code, message, details) from exc

    if region and location.get("source") == "geocoding":
        _cache_store(region, location, source_calls)

    return {
        "location": location,
        "source_calls": source_calls,
    }


def _fetch_onecall_daily(
    *,
    region: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    start_date: date,
    end_date: date,
    units: str = "metric",
    lang: str = "zh_cn",
) -> Dict[str, Any]:
    """Fetch daily forecast from OpenWeather /onecall endpoint (daily field contains weather info)."""
    # Use query_weather without time parameters to get /onecall response with daily forecast
    result = query_weather(
        region=region,
        lat=lat,
        lon=lon,
        units=units,
        lang=lang,
    )
    if result.get("errors"):
        raise _extract_error(result)

    # Extract daily forecasts within the requested date range
    location = result.get("location") or {}
    raw_data = result.get("data") or {}
    daily_list = raw_data.get("daily", [])

    days = []

    # Use UTC for date calculations since the API returns UTC timestamps
    # The dt field in daily forecast represents 00:00:00 UTC for that day
    for day_item in daily_list:
        # Get the date from the daily item
        dt_epoch = day_item.get("dt")
        if not dt_epoch:
            continue

        # Convert UTC timestamp to date (the API dt represents the date at 00:00 UTC)
        # For Beijing (UTC+8), 00:00 UTC = 08:00 same day Beijing time
        day_date = datetime.fromtimestamp(dt_epoch, tz=timezone.utc).date()

        # Only include days within the requested range
        if day_date < start_date or day_date > end_date:
            continue

        # Extract weather info from the daily item
        weather_list = day_item.get("weather", [])
        weather_info = weather_list[0] if weather_list else {}

        # Extract temperature data
        temp = day_item.get("temp", {})

        # Extract other weather data
        days.append({
            "date": day_date.isoformat(),
            "t_min": temp.get("min"),
            "t_max": temp.get("max"),
            "t_morning": temp.get("morn"),
            "t_afternoon": temp.get("day"),
            "t_evening": temp.get("eve"),
            "t_night": temp.get("night"),
            "precip_total": day_item.get("rain", 0) + day_item.get("snow", 0),
            "wind_max": day_item.get("wind_speed"),
            "wind_dir": day_item.get("wind_deg"),
            "humidity_afternoon": day_item.get("humidity"),
            "cloud_cover_afternoon": day_item.get("clouds"),
            "pressure_afternoon": day_item.get("pressure"),
            "weather_id": weather_info.get("id"),
            "weather_main": weather_info.get("main"),
            "weather_description": weather_info.get("description"),
            "weather_icon": weather_info.get("icon"),
            "source": "open_weather",
        })

    return {
        "location": {"lat": location.get("lat"), "lon": location.get("lon"), **location},
        "time_window": result.get("time_window") or {},
        "source_calls": result.get("source_calls") or [],
        "days": days,
        "raw": raw_data,
    }


def fetch_short_forecast(
    *,
    region: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    start_date: date,
    end_date: date,
    units: str = "metric",
    lang: str = "zh_cn",
) -> Dict[str, Any]:
    """Fetch short-term daily forecast from OpenWeather /onecall endpoint with weather info."""
    # Use the new _fetch_onecall_daily function to get weather data from /onecall endpoint
    return _fetch_onecall_daily(
        region=region,
        lat=lat,
        lon=lon,
        start_date=start_date,
        end_date=end_date,
        units=units,
        lang=lang,
    )
