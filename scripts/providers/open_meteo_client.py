#!/usr/bin/env python3
"""Open-Meteo provider with model fallback and retry."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG = {
    "timezone": "Asia/Shanghai",
    "providers": {
        "weather_source_mode": "open_meteo_all",
    },
    "geocoding_cache": {
        "enabled": True,
        "file": ".cache/openweather_geocoding_cache.json",
    },
    "models": ["ecmwf_ifs", "cma_grapes_global"],
    "hourly_variables": [
        "temperature_2m",
        "relative_humidity_2m",
        "weather_code",
        "precipitation",
        "wind_speed_10m",
        "wind_direction_10m",
        "visibility",
        "apparent_temperature",
    ],
    "retry": {"max_retries": 5, "backoff_factor": 0.2},
    "api": {"base_url": "https://api.open-meteo.com/v1/forecast", "timeout_seconds": 30},
    "key_hours": [9, 15, 21],
    "rounding": {
        "temperature": 1,
        "precipitation": 1,
        "wind_speed": 1,
        "humidity": 0,
    },
    "report": {
        "city": "Beijing",
        "timezone": "Asia/Shanghai",
        "include_holiday": True,
        "source_cn": "OpenWeather + Open-Meteo",
        "updated_at_format": "%Y-%m-%d %H:%M:%S",
        "webhook": {
            "url": "",
            "timeout_seconds": 10,
            "max_retries": 2,
            "retry_backoff_seconds": 1.5,
        },
        "defaults": {
            "weather_source_mode": "open_meteo_all",
        },
    },
}

WMO_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class OpenMeteoProviderError(RuntimeError):
    """Provider-level wrapper for Open-Meteo failures."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _merge_dict(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(default)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(default.get(key), dict):
            merged[key] = _merge_dict(default[key], value)
        else:
            merged[key] = value
    return merged


def _load_dotenv() -> None:
    script_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path.cwd() / ".env",
        script_root / ".env",
        Path.home() / ".openclaw" / "skills" / "weather-forecast-fusion" / ".env",
    ]
    seen = set()
    for path in candidates:
        resolved = str(path.resolve()) if path.exists() else str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    lowered = text.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _load_yaml_fallback(path: Path) -> Dict[str, Any]:
    """Minimal YAML loader for nested mappings used by this project."""
    root: Dict[str, Any] = {}
    stack: List[tuple[int, Dict[str, Any]]] = [(-1, root)]

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if raw_value == "":
            child: Dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
            continue
        current[key] = _parse_scalar(raw_value)

    return root


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    _load_dotenv()
    path_text = config_path or os.getenv("FUSION_CONFIG_FILE", "").strip()
    if path_text:
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    else:
        path = Path(__file__).resolve().parents[2] / "config" / "fusion_config.yaml"
    if not path.exists():
        config = dict(DEFAULT_CONFIG)
    else:
        try:
            import yaml  # type: ignore

            with path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if not isinstance(loaded, dict):
                config = dict(DEFAULT_CONFIG)
            else:
                config = _merge_dict(DEFAULT_CONFIG, loaded)
        except Exception:
            try:
                loaded = _load_yaml_fallback(path)
                config = _merge_dict(DEFAULT_CONFIG, loaded if isinstance(loaded, dict) else {})
            except Exception:
                config = dict(DEFAULT_CONFIG)

    timeout_text = os.getenv("OPENMETEO_TIMEOUT_SECONDS", "").strip()
    if timeout_text:
        try:
            config["api"]["timeout_seconds"] = int(timeout_text)
        except Exception:
            pass
    return config


def wmo_description(code: Any) -> str:
    try:
        return WMO_CODES.get(int(code), f"Unknown ({code})")
    except Exception:
        return "Unknown"


def _fetch_json(url: str, params: Dict[str, Any], *, max_retries: int, backoff_factor: float, timeout: int) -> Dict[str, Any]:
    query_parts: List[str] = []
    for key, value in params.items():
        if isinstance(value, list):
            query_parts.append(f"{key}={','.join(str(v) for v in value)}")
        else:
            query_parts.append(f"{key}={value}")

    full_url = f"{url}?{'&'.join(query_parts)}"
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(full_url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            if data.get("error"):
                raise RuntimeError(data.get("reason", "Open-Meteo API returned error"))
            return data
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(backoff_factor * (2 ** (attempt - 1)))

    raise OpenMeteoProviderError(
        "OPENMETEO_REQUEST_FAILED",
        "Open-Meteo request failed after retries",
        {"error": str(last_exc) if last_exc else "unknown"},
    )


def fetch_long_forecast(
    *,
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    timezone: str = "Asia/Shanghai",
) -> Dict[str, Any]:
    config = load_config()
    models = config.get("models") or DEFAULT_CONFIG["models"]
    retry = config.get("retry") or {}
    api = config.get("api") or {}
    hourly_vars = config.get("hourly_variables") or DEFAULT_CONFIG["hourly_variables"]

    errors: List[Dict[str, Any]] = []
    for model in models:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": hourly_vars,
            "timezone": timezone,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "models": model,
        }
        try:
            raw = _fetch_json(
                api.get("base_url", DEFAULT_CONFIG["api"]["base_url"]),
                params,
                max_retries=int(retry.get("max_retries", DEFAULT_CONFIG["retry"]["max_retries"])),
                backoff_factor=float(retry.get("backoff_factor", DEFAULT_CONFIG["retry"]["backoff_factor"])),
                timeout=int(api.get("timeout_seconds", DEFAULT_CONFIG["api"]["timeout_seconds"])),
            )
            return {
                "model": model,
                "raw": raw,
                "source_call": {
                    "endpoint": api.get("base_url", DEFAULT_CONFIG["api"]["base_url"]),
                    "params": params,
                },
                "config": config,
            }
        except OpenMeteoProviderError as exc:
            errors.append({"model": model, "code": exc.code, "message": exc.message, "details": exc.details})

    raise OpenMeteoProviderError(
        "UPSTREAM_OPENMETEO_FAILED",
        "All Open-Meteo models failed",
        {"errors": errors},
    )
