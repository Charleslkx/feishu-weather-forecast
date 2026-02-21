#!/usr/bin/env python3
"""OpenWeather query tool with UTC+8 normalized output."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

UTC = timezone.utc
UTC8 = timezone(timedelta(hours=8))
ONECALL_BASE = "https://api.openweathermap.org/data/3.0"
GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
DEFAULT_TIMEOUT = 30
SKILL_NAME = "weather-forecast-fusion"

EPOCH_KEYS = {
    "dt",
    "sunrise",
    "sunset",
    "moonrise",
    "moonset",
    "start",
    "end",
}


class WeatherQueryError(Exception):
    """Error with a public error code and message."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _load_dotenv(dotenv_path: str = ".env") -> None:
    script_root = Path(__file__).resolve().parent.parent
    candidates = [
        Path(dotenv_path),
        Path.cwd() / ".env",
        script_root / ".env",
        Path.home() / ".openclaw" / "skills" / SKILL_NAME / ".env",
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


def _get_settings() -> Tuple[str, int]:
    _load_dotenv()
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    timeout_raw = os.getenv("OPENWEATHER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)).strip()
    try:
        timeout = int(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    return api_key, timeout


def _epoch_to_utc8_iso(epoch_seconds: int) -> str:
    dt = datetime.fromtimestamp(int(epoch_seconds), tz=UTC)
    return dt.astimezone(UTC8).isoformat()


def _parse_datetime_input(value: Any, field_name: str) -> datetime:
    if value is None:
        raise WeatherQueryError("INVALID_TIME", f"{field_name} 不能为空")

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC8)
        return dt.astimezone(UTC8)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=UTC).astimezone(UTC8)

    text = str(value).strip()
    if not text:
        raise WeatherQueryError("INVALID_TIME", f"{field_name} 不能为空")

    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=UTC).astimezone(UTC8)

    # Common formats without timezone: interpret as UTC+8.
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                parsed = datetime.combine(parsed.date(), dtime.min)
            return parsed.replace(tzinfo=UTC8)
        except ValueError:
            continue

    # ISO-8601 support.
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC8)
        return parsed.astimezone(UTC8)
    except ValueError as exc:
        raise WeatherQueryError(
            "INVALID_TIME",
            f"{field_name} 格式不正确，支持 epoch 或常见日期时间字符串",
            {"field": field_name, "value": text},
        ) from exc


def _parse_date_input(value: Any, field_name: str) -> date:
    dt = _parse_datetime_input(value, field_name)
    return dt.astimezone(UTC8).date()


def _request_json(url: str, params: Dict[str, Any], timeout: int) -> Any:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "OpenClaw-OpenWeather/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        parsed: Dict[str, Any] = {}
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw or str(exc)}

        message = parsed.get("message") or str(exc)
        status = exc.code
        if status == 400:
            code = "OPENWEATHER_400"
        elif status == 401:
            code = "OPENWEATHER_401"
        elif status == 404:
            code = "OPENWEATHER_404"
        elif status == 429:
            code = "OPENWEATHER_429"
        elif 500 <= status < 600:
            code = "OPENWEATHER_5XX"
        else:
            code = "OPENWEATHER_HTTP_ERROR"

        raise WeatherQueryError(code, f"OpenWeather API 错误: {message}", {"status": status, "payload": parsed}) from exc
    except urllib.error.URLError as exc:
        raise WeatherQueryError("NETWORK_ERROR", f"网络请求失败: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise WeatherQueryError("INVALID_RESPONSE", "OpenWeather 返回了非 JSON 数据") from exc


def _call_openweather(
    path: str,
    params: Dict[str, Any],
    api_key: str,
    timeout: int,
    source_calls: List[Dict[str, Any]],
) -> Any:
    full_params = {k: v for k, v in params.items() if v is not None}
    full_params["appid"] = api_key
    source_calls.append(
        {
            "endpoint": f"{ONECALL_BASE}{path}",
            "params": {k: v for k, v in full_params.items() if k != "appid"},
        }
    )
    return _request_json(f"{ONECALL_BASE}{path}", full_params, timeout)


def _normalize_region_text(region: str) -> str:
    text = region.strip().replace("，", ",")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(", ").strip()


def _normalize_match_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("，", ",")
    text = re.sub(r"[\s,_-]+", "", text)
    return text


def _split_region_hints(region: str) -> Tuple[str, Optional[str]]:
    normalized = _normalize_region_text(region)
    if not normalized:
        return "", None

    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if not parts:
        return "", None

    city_hint = parts[0]
    province_hint = ", ".join(parts[1:]) if len(parts) > 1 else None
    return city_hint, province_hint


def _province_match_level(candidate: Dict[str, Any], province_hint: Optional[str]) -> int:
    if not province_hint:
        return 0

    state = _normalize_match_token(candidate.get("state", ""))
    province = _normalize_match_token(province_hint)
    if not state or not province:
        return 0
    if state == province:
        return 2
    if province in state or state in province:
        return 1
    return 0


def _score_candidate(candidate: Dict[str, Any], city_hint: str, province_hint: Optional[str]) -> int:
    city = _normalize_match_token(city_hint)
    name = _normalize_match_token(candidate.get("name", ""))
    score = 0

    if city and name == city:
        score += 100
    elif city and city in name:
        score += 40

    province_level = _province_match_level(candidate, province_hint)
    if province_hint:
        if province_level == 2:
            score += 120
        elif province_level == 1:
            score += 80
        else:
            score -= 60

    if candidate.get("country") == "CN":
        score += 10
    return score


def _build_region_queries(region: str) -> List[str]:
    normalized = _normalize_region_text(region)
    if not normalized:
        return []

    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    queries: List[str] = []

    # Priority 1: full composite query, e.g. "Guiyang, Guizhou".
    if len(parts) >= 2:
        queries.append(", ".join(parts))
        # Priority 2: city only fallback for better recall.
        queries.append(parts[0])
    else:
        queries.append(parts[0])

    # Deduplicate while preserving order.
    seen = set()
    deduped: List[str] = []
    for query in queries:
        if query not in seen:
            deduped.append(query)
            seen.add(query)
    return deduped


def _resolve_location(
    region: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    api_key: str,
    timeout: int,
    source_calls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if lat is not None and lon is not None:
        return {
            "lat": float(lat),
            "lon": float(lon),
            "input_region": region,
            "resolved_location": None,
            "source": "latlon",
        }

    if (lat is None) != (lon is None):
        raise WeatherQueryError("MISSING_LOCATION", "lat 与 lon 需要同时提供")

    if not region or not str(region).strip():
        raise WeatherQueryError("MISSING_LOCATION", "必须提供 region 或 lat/lon")

    city_hint, province_hint = _split_region_hints(region)
    queries = _build_region_queries(region)
    if not queries:
        raise WeatherQueryError("MISSING_LOCATION", "region 不能为空")

    first: Optional[Dict[str, Any]] = None
    for query_text in queries:
        params = {"q": query_text, "limit": 5, "appid": api_key}
        source_calls.append(
            {
                "endpoint": GEOCODING_URL,
                "params": {"q": params["q"], "limit": 5},
            }
        )
        result = _request_json(GEOCODING_URL, params, timeout)
        if isinstance(result, list) and result:
            if province_hint:
                matched = [c for c in result if _province_match_level(c, province_hint) > 0]
                if matched:
                    first = max(matched, key=lambda c: _score_candidate(c, city_hint, province_hint))
                    break
                # Keep trying fallback queries instead of selecting mismatched province.
                continue

            first = max(result, key=lambda c: _score_candidate(c, city_hint, None))
            break

    if not first:
        if province_hint:
            raise WeatherQueryError("LOCATION_NOT_FOUND", f"未找到匹配省份的地区: {region}")
        raise WeatherQueryError("LOCATION_NOT_FOUND", f"未找到地区: {region}")

    resolved_name = ", ".join(
        part
        for part in [
            first.get("name"),
            first.get("state"),
            first.get("country"),
        ]
        if part
    )

    return {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "input_region": region,
        "resolved_location": resolved_name or None,
        "source": "geocoding",
    }


def _augment_timestamps(value: Any) -> Any:
    if isinstance(value, list):
        return [_augment_timestamps(item) for item in value]

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[key] = _augment_timestamps(item)
            if key in EPOCH_KEYS and isinstance(item, (int, float)):
                out[f"{key}_utc8"] = _epoch_to_utc8_iso(int(item))
        return out

    return value


def _daterange(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _build_summary(mode: str, payload: Dict[str, Any]) -> str:
    location = payload.get("location", {})
    loc_text = location.get("resolved_location") or location.get("input_region")
    if not loc_text and location.get("lat") is not None and location.get("lon") is not None:
        loc_text = f"{location.get('lat')}, {location.get('lon')}"
    if not loc_text:
        loc_text = "目标地区"

    if payload.get("errors"):
        return f"{loc_text} 查询失败：{payload['errors'][0]['message']}"

    if mode == "current_forecast":
        current = (payload.get("data") or {}).get("current", {})
        temp = current.get("temp")
        desc = ""
        weather_items = current.get("weather") or []
        if weather_items:
            desc = weather_items[0].get("description", "")
        temp_text = f"{temp}°" if temp is not None else "温度未知"
        return f"{loc_text} 当前天气：{desc or '未知'}，气温 {temp_text}。"

    if mode == "single_time":
        target = payload.get("time_window", {}).get("target_time_utc8", "")
        data = payload.get("data") or {}
        point = data.get("data", [{}])[0] if isinstance(data.get("data"), list) and data.get("data") else data
        temp = point.get("temp")
        return f"{loc_text} 在 {target} 的历史天气已查询，气温 {temp if temp is not None else '未知'}。"

    if mode == "time_range":
        days = (payload.get("data") or {}).get("days", [])
        return f"{loc_text} 在时间区间内共查询 {len(days)} 天的天气聚合数据。"

    return f"{loc_text} 天气查询完成。"


def query_weather(
    region: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    time: Optional[Any] = None,
    start_time: Optional[Any] = None,
    end_time: Optional[Any] = None,
    units: str = "metric",
    lang: str = "zh_cn",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "query": {
            "region": region,
            "lat": lat,
            "lon": lon,
            "time": time,
            "start_time": start_time,
            "end_time": end_time,
            "units": units,
            "lang": lang,
        },
        "location": {},
        "time_window": {},
        "source_calls": [],
        "data": {},
        "summary_zh": "",
        "errors": [],
    }

    try:
        api_key, timeout = _get_settings()
        if not api_key:
            raise WeatherQueryError("MISSING_API_KEY", "未在 .env 或环境变量中找到 OPENWEATHER_API_KEY")

        if time is not None and (start_time is not None or end_time is not None):
            raise WeatherQueryError("INVALID_TIME", "time 与 start_time/end_time 不能同时使用")

        if (start_time is None) != (end_time is None):
            raise WeatherQueryError("INVALID_TIME_RANGE", "start_time 与 end_time 必须同时提供")

        location = _resolve_location(region, lat, lon, api_key, timeout, payload["source_calls"])
        payload["location"] = location

        if time is None and start_time is None:
            mode = "current_forecast"
            raw = _call_openweather(
                "/onecall",
                {
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "units": units,
                    "lang": lang,
                },
                api_key,
                timeout,
                payload["source_calls"],
            )
            payload["data"] = _augment_timestamps(raw)
            payload["time_window"] = {"mode": mode, "timezone": "UTC+08:00"}

        elif time is not None:
            mode = "single_time"
            target_dt = _parse_datetime_input(time, "time")
            dt_epoch = int(target_dt.astimezone(UTC).timestamp())
            raw = _call_openweather(
                "/onecall/timemachine",
                {
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "dt": dt_epoch,
                    "units": units,
                    "lang": lang,
                },
                api_key,
                timeout,
                payload["source_calls"],
            )
            payload["data"] = _augment_timestamps(raw)
            payload["time_window"] = {
                "mode": mode,
                "target_time_utc8": target_dt.isoformat(),
                "target_time_epoch": dt_epoch,
                "timezone": "UTC+08:00",
            }

        else:
            mode = "time_range"
            start_date = _parse_date_input(start_time, "start_time")
            end_date = _parse_date_input(end_time, "end_time")
            if start_date > end_date:
                raise WeatherQueryError("INVALID_TIME_RANGE", "start_time 不能晚于 end_time")

            days: List[Dict[str, Any]] = []
            for day in _daterange(start_date, end_date):
                day_text = day.isoformat()
                raw = _call_openweather(
                    "/onecall/day_summary",
                    {
                        "lat": location["lat"],
                        "lon": location["lon"],
                        "date": day_text,
                        "tz": "+08:00",
                        "units": units,
                    },
                    api_key,
                    timeout,
                    payload["source_calls"],
                )
                days.append({"date": day_text, "summary": _augment_timestamps(raw)})

            payload["data"] = {"days": days}
            payload["time_window"] = {
                "mode": mode,
                "start_date_utc8": start_date.isoformat(),
                "end_date_utc8": end_date.isoformat(),
                "days_count": len(days),
                "timezone": "UTC+08:00",
            }

        payload["summary_zh"] = _build_summary(payload["time_window"].get("mode", ""), payload)
        return payload

    except WeatherQueryError as exc:
        payload["errors"].append({"code": exc.code, "message": exc.message, "details": exc.details})
        payload["summary_zh"] = _build_summary(payload.get("time_window", {}).get("mode", ""), payload)
        return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenWeather 查询脚本（UTC+8）")
    parser.add_argument("--region", help="地区名，如: Beijing")
    parser.add_argument("--lat", type=float, help="纬度")
    parser.add_argument("--lon", type=float, help="经度")
    parser.add_argument("--time", help="单时间查询，支持 epoch 或日期字符串")
    parser.add_argument("--start-time", help="时间区间开始")
    parser.add_argument("--end-time", help="时间区间结束")
    parser.add_argument("--units", default="metric", help="单位：standard/metric/imperial")
    parser.add_argument("--lang", default="zh_cn", help="语言代码，默认 zh_cn")
    parser.add_argument("--json-only", action="store_true", help="只输出 JSON")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    result = query_weather(
        region=args.region,
        lat=args.lat,
        lon=args.lon,
        time=args.time,
        start_time=args.start_time,
        end_time=args.end_time,
        units=args.units,
        lang=args.lang,
    )

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("summary_zh", ""))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
