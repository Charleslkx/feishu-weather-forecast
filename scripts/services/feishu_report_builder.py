#!/usr/bin/env python3
"""Build Feishu weather report payload from fused forecast data."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

UTC8 = timezone(timedelta(hours=8))
WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

WEATHER_ICON_BY_CATEGORY = {
    "雷": "⛈️",
    "大雨": "🌧️🌧️🌧️",
    "中雨": "🌧️🌧️",
    "小雨": "🌧️",
    "雪": "❄️",
    "雾霾": "🌫️",
    "多云": "⛅",
    "阴": "☁️",
    "晴": "☀️",
    "未知": "☁️",
}

WMO_CATEGORY_MAP = {
    0: "晴",
    1: "多云",
    2: "多云",
    3: "阴",
    45: "雾霾",
    48: "雾霾",
    51: "小雨",
    53: "中雨",
    55: "中雨",
    56: "小雨",
    57: "中雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "中雨",
    67: "大雨",
    71: "雪",
    73: "雪",
    75: "雪",
    77: "雪",
    80: "小雨",
    81: "中雨",
    82: "大雨",
    85: "雪",
    86: "雪",
    95: "雷",
    96: "雷",
    99: "雷",
}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _format_temp(value: Any) -> str:
    num = _to_float(value)
    if num is None:
        return "--"
    return str(int(round(num)))


def _round_temp(value: Any) -> Optional[int]:
    num = _to_float(value)
    if num is None:
        return None
    return int(round(num))


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _weekday_text(day_value: date) -> str:
    return WEEKDAY_CN[day_value.weekday()]


def _icon_for(category: str) -> str:
    return WEATHER_ICON_BY_CATEGORY.get(category, WEATHER_ICON_BY_CATEGORY["未知"])


def _category_from_openweather_id(weather_id: int) -> str:
    if 200 <= weather_id <= 299:
        return "雷"
    if weather_id in {502, 503, 504, 522, 531}:
        return "大雨"
    if weather_id in {501, 521}:
        return "中雨"
    if 300 <= weather_id <= 499 or weather_id in {500, 520}:
        return "小雨"
    if 600 <= weather_id <= 699:
        return "雪"
    if 700 <= weather_id <= 799:
        return "雾霾"
    if weather_id == 800:
        return "晴"
    if weather_id in {801, 802}:
        return "多云"
    if weather_id in {803, 804}:
        return "阴"
    return "未知"


def weather_to_cn_icon(
    *,
    weather_code: Any = None,
    weather_id: Any = None,
    weather_main: Any = None,
    description: Any = None,
) -> Tuple[str, str]:
    code = _safe_int(weather_code)
    if code is not None and code in WMO_CATEGORY_MAP:
        category = WMO_CATEGORY_MAP[code]
        return category, _icon_for(category)

    ow_id = _safe_int(weather_id)
    if ow_id is not None:
        category = _category_from_openweather_id(ow_id)
        return category, _icon_for(category)

    text = " ".join(str(v) for v in [weather_main or "", description or ""]).lower()
    if any(k in text for k in ["thunder", "雷"]):
        return "雷", _icon_for("雷")
    if any(k in text for k in ["heavy rain", "大雨", "暴雨"]):
        return "大雨", _icon_for("大雨")
    if any(k in text for k in ["moderate rain", "中雨"]):
        return "中雨", _icon_for("中雨")
    if any(k in text for k in ["drizzle", "light rain", "小雨", "毛毛雨", "阵雨"]):
        return "小雨", _icon_for("小雨")
    if any(k in text for k in ["snow", "雪", "sleet"]):
        return "雪", _icon_for("雪")
    if any(k in text for k in ["fog", "mist", "haze", "smoke", "雾", "霾"]):
        return "雾霾", _icon_for("雾霾")
    if any(k in text for k in ["partly cloudy", "few clouds", "scattered clouds", "多云"]):
        return "多云", _icon_for("多云")
    if any(k in text for k in ["overcast", "broken clouds", "阴"]):
        return "阴", _icon_for("阴")
    if any(k in text for k in ["clear", "晴"]):
        return "晴", _icon_for("晴")
    return "未知", _icon_for("未知")


def _day_weather(day: Dict[str, Any]) -> Tuple[str, str]:
    return weather_to_cn_icon(
        weather_code=day.get("dominant_weather_code"),
        weather_id=day.get("weather_id"),
        weather_main=day.get("weather_main"),
        description=day.get("dominant_weather") or day.get("weather_description"),
    )


def _extract_hour(record: Dict[str, Any]) -> int:
    time_text = str(record.get("time") or "")
    if len(time_text) >= 13:
        try:
            return int(time_text[11:13])
        except Exception:
            return -1
    return -1


def _pick_key_hour_record(day: Dict[str, Any], target_hour: int) -> Optional[Dict[str, Any]]:
    points = day.get("key_hours") or []
    if not isinstance(points, list) or not points:
        return None

    exact = [item for item in points if isinstance(item, dict) and _extract_hour(item) == target_hour]
    if exact:
        return exact[0]

    candidates = [item for item in points if isinstance(item, dict) and _extract_hour(item) >= 0]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(_extract_hour(item) - target_hour))


def _first_existing(day: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if day.get(key) is not None:
            return day.get(key)
    return None


def _hour_slot_for_tomorrow(day: Dict[str, Any], target_hour: int) -> Dict[str, Any]:
    record = _pick_key_hour_record(day, target_hour)
    if isinstance(record, dict):
        temp = record.get("temperature")
        weather_cn, icon = weather_to_cn_icon(
            weather_code=record.get("weather_code"),
            description=record.get("weather_description"),
        )
        return {"temp_text": _format_temp(temp), "weather_cn": weather_cn, "icon": icon}

    fallback_temp_keys = {
        9: ("t_morning", "t_min", "t_max"),
        15: ("t_afternoon", "t_max", "t_min"),
        21: ("t_evening", "t_night", "t_min"),
    }
    temp = _first_existing(day, fallback_temp_keys.get(target_hour, ("t_min", "t_max")))
    weather_cn, icon = _day_weather(day)
    return {"temp_text": _format_temp(temp), "weather_cn": weather_cn, "icon": icon}


def _lookup_holiday_text(day: Dict[str, Any], date_text: str) -> str:
    if day.get("holiday"):
        return str(day.get("holiday"))
    try:
        try:
            from scripts.holiday_fetch import get_holiday_info  # type: ignore
        except ImportError:
            from holiday_fetch import get_holiday_info  # type: ignore
        value = get_holiday_info(date_text)
        return str(value) if value else ""
    except Exception:
        return ""


def _merge_days(forecast_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    days_map: Dict[str, Dict[str, Any]] = {}
    short_days = (forecast_result.get("forecast_short_open_weather") or {}).get("days") or []
    long_days = (forecast_result.get("forecast_long_open_meteo") or {}).get("days") or []
    for item in list(short_days) + list(long_days):
        if not isinstance(item, dict):
            continue
        date_text = item.get("date")
        if not date_text:
            continue
        days_map[str(date_text)] = item
    return days_map


def _attach_temp_alerts(rows: List[Dict[str, Any]]) -> None:
    # Rules (life-oriented):
    # 1) Day-over-day strong change (Tmax): >= 5°C => ⏫ / <= -5°C => ⏬
    # 2) Same-day temperature range (Tmax - Tmin): >= 10°C => ⚠️
    # 3) Lifestyle trend (lookback, already-formed trend):
    #    I = 0.6*Tmax + 0.4*Tmin
    #    In last 3 days, at least 2 day-to-day moves share direction,
    #    and total ΔI (today vs t-3) >= 4 => 📈, <= -4 => 📉
    day_threshold = 5.0
    range_threshold = 10.0
    trend_threshold = 4.0

    def _index_value(day: Dict[str, Any]) -> float:
        return 0.6 * float(day["max"]) + 0.4 * float(day["min"])

    for i in range(len(rows)):
        alerts: List[str] = []
        curr = rows[i]
        tmax = curr.get("max")
        tmin = curr.get("min")

        if not isinstance(tmax, (int, float)) or isinstance(tmax, bool):
            curr["alerts"] = []
            curr["alerts_text"] = ""
            continue
        if not isinstance(tmin, (int, float)) or isinstance(tmin, bool):
            curr["alerts"] = []
            curr["alerts_text"] = ""
            continue

        # 1) day-over-day strong change (Tmax)
        if i > 0:
            prev_max = rows[i - 1].get("max")
            if isinstance(prev_max, (int, float)) and not isinstance(prev_max, bool):
                dmax = float(tmax) - float(prev_max)
                if dmax >= day_threshold:
                    alerts.append("⏫")
                elif dmax <= -day_threshold:
                    alerts.append("⏬")

        # 2) same-day range
        if (float(tmax) - float(tmin)) >= range_threshold:
            alerts.append("⚠️")

        # 3) lifestyle trend (lookback 3 days)
        if i >= 3:
            d1 = _index_value(rows[i - 2]) - _index_value(rows[i - 3])
            d2 = _index_value(rows[i - 1]) - _index_value(rows[i - 2])
            d3 = _index_value(rows[i]) - _index_value(rows[i - 1])

            up_days = sum(d > 0 for d in (d1, d2, d3))
            down_days = sum(d < 0 for d in (d1, d2, d3))
            total = _index_value(rows[i]) - _index_value(rows[i - 3])

            if up_days >= 2 and total >= trend_threshold:
                alerts.append("📈")
            elif down_days >= 2 and total <= -trend_threshold:
                alerts.append("📉")

        curr["alerts"] = alerts
        curr["alerts_text"] = " ".join(alerts)


def render_report_text(
    *,
    city: str,
    tomorrow_slots: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
    updated_at_cn: str,
    source_cn: str,
) -> str:
    del city  # Template intentionally does not render city line.
    del source_cn  # `source_cn` is kept in payload field but omitted in text block.
    lines: List[str] = [
        "**明日分时详情**",
        "",
        f"- 早晨（09:00） {tomorrow_slots['09']['temp_text']}°C | {tomorrow_slots['09']['weather_cn']}",
        f"- 中午（15:00） {tomorrow_slots['15']['temp_text']}°C | {tomorrow_slots['15']['weather_cn']}",
        f"- 晚上（21:00） {tomorrow_slots['21']['temp_text']}°C | {tomorrow_slots['21']['weather_cn']}",
        "",
        "---",
        "",
        "**未来 7 天趋势预览**",
        "",
    ]
    for row in rows:
        line = (
            f"{row['date_label']} {row['weekday']}{row['holiday_opt']} {row['icon']} "
            f"{row['min_text']}°C ～ {row['max_text']}°C {row['weather_cn']}"
        )
        if row.get("alerts_text"):
            line = f"{line} {row['alerts_text']}"
        lines.append(line)
    lines.extend(["", "---", ""])
    lines.extend(["⏫ / ⏬ → T vs T-1", "📈 / 📉 → 最近几天已经形成趋势", "⚠️ → 昼夜温差大", ""])
    lines.append(f"更新于：{updated_at_cn}（UTC+8）")
    return "\n".join(lines)


def build_payload_from_forecast(
    *,
    forecast_result: Dict[str, Any],
    city: str,
    source_cn: str,
    updated_at_cn: str,
    include_holiday: bool,
    today_utc8: Optional[date] = None,
) -> Dict[str, Any]:
    today = today_utc8 or datetime.now(UTC8).date()
    start = today + timedelta(days=1)
    days_map = _merge_days(forecast_result)

    rows: List[Dict[str, Any]] = []
    for offset in range(7):
        target_date = start + timedelta(days=offset)
        date_text = target_date.isoformat()
        row_day = days_map.get(date_text, {})
        weather_cn, icon = _day_weather(row_day)
        holiday = _lookup_holiday_text(row_day, date_text) if include_holiday else ""
        rows.append(
            {
                "date_iso": date_text,
                "date_label": target_date.strftime("%m-%d"),
                "weekday": _weekday_text(target_date),
                "holiday": holiday,
                "holiday_opt": f" {holiday}" if holiday else "",
                "min": _round_temp(row_day.get("t_min")),
                "max": _round_temp(row_day.get("t_max")),
                "min_text": _format_temp(row_day.get("t_min")),
                "max_text": _format_temp(row_day.get("t_max")),
                "weather_cn": weather_cn,
                "icon": icon,
            }
        )

    _attach_temp_alerts(rows)

    tomorrow_day = days_map.get(start.isoformat(), {})
    tomorrow_slots = {
        "09": _hour_slot_for_tomorrow(tomorrow_day, 9),
        "15": _hour_slot_for_tomorrow(tomorrow_day, 15),
        "21": _hour_slot_for_tomorrow(tomorrow_day, 21),
    }

    report_text = render_report_text(
        city=city,
        tomorrow_slots=tomorrow_slots,
        rows=rows,
        updated_at_cn=updated_at_cn,
        source_cn=source_cn,
    )

    payload_days = [
        {
            "date": row["date_label"],
            "date_iso": row["date_iso"],
            "weekday": row["weekday"],
            "holiday": row["holiday"],
            "min": row["min"],
            "max": row["max"],
            "weather_cn": row["weather_cn"],
            "icon": row["icon"],
            "alerts": row.get("alerts", []),
        }
        for row in rows
    ]

    errors = forecast_result.get("errors") or []
    return {
        "message_type": "text",
        "report_text": report_text,
        "report_lines": report_text.split("\n"),
        "city": city,
        "updated_at_cn": updated_at_cn,
        "source_cn": source_cn,
        "days": payload_days,
        "has_partial_data": bool(errors),
        "errors": errors,
    }
