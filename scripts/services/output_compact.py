#!/usr/bin/env python3
"""Token-efficient output builders for fused forecast."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

try:
    from scripts.providers.open_meteo_client import wmo_description
except ImportError:
    from providers.open_meteo_client import wmo_description


def _round(value: Any, ndigits: int) -> Any:
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except Exception:
        return value


def _to_hour(time_text: str) -> int:
    # "2026-02-10T15:00"
    try:
        return int(time_text[11:13])
    except Exception:
        return -1


def compact_open_meteo_hourly_to_daily(
    raw: Dict[str, Any], key_hours: List[int], rounding: Dict[str, int]
) -> Dict[str, Any]:
    hourly = raw.get("hourly") or {}
    units = raw.get("hourly_units") or {}
    times: List[str] = hourly.get("time") or []
    if not times:
        return {"days": [], "units": units}

    days_index: Dict[str, List[int]] = {}
    for idx, time_text in enumerate(times):
        day_key = time_text[:10]
        days_index.setdefault(day_key, []).append(idx)

    days: List[Dict[str, Any]] = []
    for day_key, indices in sorted(days_index.items()):
        temps = [hourly.get("temperature_2m", [None])[i] for i in indices if i < len(hourly.get("temperature_2m", []))]
        precips = [hourly.get("precipitation", [None])[i] for i in indices if i < len(hourly.get("precipitation", []))]
        winds = [hourly.get("wind_speed_10m", [None])[i] for i in indices if i < len(hourly.get("wind_speed_10m", []))]
        codes = [hourly.get("weather_code", [None])[i] for i in indices if i < len(hourly.get("weather_code", []))]

        temps = [v for v in temps if v is not None]
        precips = [v for v in precips if v is not None]
        winds = [v for v in winds if v is not None]
        codes = [v for v in codes if v is not None]

        dominant_code = Counter(codes).most_common(1)[0][0] if codes else None

        key_points: List[Dict[str, Any]] = []
        for i in indices:
            hour = _to_hour(times[i])
            if hour not in key_hours:
                continue
            record = {
                "time": times[i],
                "temperature": _round(hourly.get("temperature_2m", [None])[i], rounding.get("temperature", 1)),
                "humidity": _round(hourly.get("relative_humidity_2m", [None])[i], rounding.get("humidity", 0)),
                "precipitation": _round(hourly.get("precipitation", [None])[i], rounding.get("precipitation", 1)),
                "wind_speed": _round(hourly.get("wind_speed_10m", [None])[i], rounding.get("wind_speed", 1)),
                "weather_code": hourly.get("weather_code", [None])[i],
                "weather_description": wmo_description(hourly.get("weather_code", [None])[i]),
            }
            key_points.append(record)

        days.append(
            {
                "date": day_key,
                "t_min": _round(min(temps) if temps else None, rounding.get("temperature", 1)),
                "t_max": _round(max(temps) if temps else None, rounding.get("temperature", 1)),
                "precip_sum": _round(sum(precips) if precips else None, rounding.get("precipitation", 1)),
                "wind_max": _round(max(winds) if winds else None, rounding.get("wind_speed", 1)),
                "dominant_weather_code": dominant_code,
                "dominant_weather": wmo_description(dominant_code) if dominant_code is not None else "Unknown",
                "key_hours": key_points,
                "source": "open_meteo",
            }
        )

    return {
        "days": days,
        "units": {
            "temperature": units.get("temperature_2m", "°C"),
            "humidity": units.get("relative_humidity_2m", "%"),
            "precipitation": units.get("precipitation", "mm"),
            "wind_speed": units.get("wind_speed_10m", "km/h"),
            "time": units.get("time", "iso8601"),
        },
    }


def build_summary_en(location_text: str, short_days: List[Dict[str, Any]], long_days: List[Dict[str, Any]]) -> str:
    total = len(short_days) + len(long_days)
    if total == 0:
        return f"No forecast data available for {location_text}."

    all_days = short_days + long_days
    t_min = min([d.get("t_min") for d in all_days if d.get("t_min") is not None], default=None)
    t_max = max([d.get("t_max") for d in all_days if d.get("t_max") is not None], default=None)
    rain = sum([d.get("precip_total") or d.get("precip_sum") or 0 for d in all_days])

    date_labels = []
    for day in all_days:
        date_text = day.get("date")
        if not date_text:
            continue
        label_parts = [date_text]
        weekday_utc8 = day.get("weekday_utc8")
        holiday = day.get("holiday")
        if weekday_utc8:
            label_parts.append(f"({weekday_utc8}, UTC+8)")
        if holiday:
            label_parts.append(f"[{holiday}]")
        date_labels.append(" ".join(label_parts))

    date_suffix = f" Dates: {'; '.join(date_labels)}." if date_labels else ""

    return (
        f"Forecast for {location_text}: {total} days available. "
        f"Temperature range {t_min} to {t_max}. "
        f"Estimated total precipitation {round(rain, 1)} mm."
        f"{date_suffix}"
    )
