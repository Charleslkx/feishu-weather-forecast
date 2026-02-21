#!/usr/bin/env python3
"""下载并解析中国节假日 ICS 文件。"""

from __future__ import annotations

import gzip
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

ICS_URL = "https://calendars.icloud.com/holidays/cn_zh.ics"
SKILL_NAME = "weather-forecast-fusion"
DEFAULT_CACHE_FILE = Path.home() / ".openclaw" / "skills" / SKILL_NAME / "holidays_cache.txt"
UTC8 = timezone(timedelta(hours=8))


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


def _get_cache_file() -> Path:
    _load_dotenv()
    cache_path = os.getenv("HOLIDAY_CACHE_FILE", "").strip()
    if cache_path:
        return Path(cache_path)
    return DEFAULT_CACHE_FILE


def _decode_ics_bytes(data: bytes) -> str:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _unfold_ics_lines(content: str) -> str:
    # ICS folded lines start with space or tab and belong to previous line.
    return re.sub(r"\r?\n[ \t]", "", content)


def _extract_event_field(block: str, field_name: str) -> Optional[str]:
    pattern = rf"^{field_name}(?:;[^:]*)?:(.+)$"
    match = re.search(pattern, block, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _clean_summary(text: str) -> str:
    return (
        text.replace(r"\n", " ")
        .replace(r"\,", ",")
        .replace(r"\;", ";")
        .replace("\\", "")
        .strip()
    )


def _parse_event_date(dt_raw: str) -> Optional[datetime]:
    # Supports YYYYMMDD and datetime-like DTSTART values.
    match = re.search(r"(\d{8})", dt_raw)
    if not match:
        return None
    date_text = match.group(1)
    return datetime.strptime(date_text, "%Y%m%d")


def download_ics() -> Optional[str]:
    """下载 ICS 文件。"""
    req = urllib.request.Request(
        ICS_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/calendar, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            content_encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in content_encoding and data[:2] != b"\x1f\x8b":
                # Some servers use header but not gzip body; fallback to raw decode.
                pass
            return _decode_ics_bytes(data)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, gzip.BadGzipFile) as exc:
        print(f"下载失败: {exc}")
        return None


def parse_ics(ics_content: str) -> List[Dict[str, object]]:
    """解析 ICS 内容，提取节假日和节气。"""
    content = _unfold_ics_lines(ics_content)
    events: List[Dict[str, object]] = []

    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, flags=re.DOTALL)
    for block in blocks:
        dt_raw = _extract_event_field(block, "DTSTART")
        if not dt_raw:
            continue
        event_dt = _parse_event_date(dt_raw)
        if event_dt is None:
            continue

        title_raw = _extract_event_field(block, "SUMMARY") or "未知"
        title = _clean_summary(title_raw)
        if "（休）" in title or "（班）" in title:
            continue

        events.append(
            {
                "date": event_dt,
                "date_str": event_dt.strftime("%Y-%m-%d"),
                "title": title,
            }
        )

    events.sort(key=lambda x: x["date"])
    return events


def save_cache(events: List[Dict[str, object]]) -> bool:
    """保存到缓存文件。"""
    cache_file = _get_cache_file().expanduser()
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        updated_at = datetime.now(UTC8).strftime("%Y-%m-%d %H:%M:%S %z")
        with cache_file.open("w", encoding="utf-8") as f:
            f.write("# 中国节假日缓存\n")
            f.write(f"# 更新时间(UTC+8): {updated_at}\n\n")
            for event in events:
                f.write(f"{event['date_str']} | {event['title']}\n")
        print(f"缓存已保存: {cache_file}")
        return True
    except OSError as exc:
        print(f"保存缓存失败: {exc}")
        return False


def get_holiday_info(date_str: str) -> Optional[str]:
    """查询指定日期的节假日信息。"""
    cache_file = _get_cache_file().expanduser()
    if not cache_file.exists():
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.touch()
        except OSError:
            pass
        return None

    try:
        with cache_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split(" | ", 1)
                if len(parts) == 2 and parts[0] == date_str:
                    return parts[1]
        return None
    except OSError as exc:
        print(f"查询失败: {exc}")
        return None


def main() -> bool:
    """主函数。"""
    print("开始下载中国节假日数据...")

    ics_content = download_ics()
    if not ics_content:
        print("下载失败，尝试使用缓存")
        return False

    print(f"下载成功，数据大小: {len(ics_content)} 字符")
    print("解析 ICS 数据...")
    events = parse_ics(ics_content)
    print(f"解析完成，共 {len(events)} 个节假日/节气")

    if save_cache(events):
        print(f"已更新缓存，包含 {len(events)} 条记录")

    print("\n最近的重要日期:")
    today = datetime.now(UTC8).replace(tzinfo=None)
    upcoming = [e for e in events if e["date"] >= today][:5]
    for event in upcoming:
        days_diff = (event["date"] - today).days
        if days_diff == 0:
            when = "今天"
        elif days_diff == 1:
            when = "明天"
        else:
            when = f"{days_diff}天后"
        print(f"  {event['date_str']} ({when}): {event['title']}")

    return True


if __name__ == "__main__":
    success = main()
    raise SystemExit(0 if success else 1)
