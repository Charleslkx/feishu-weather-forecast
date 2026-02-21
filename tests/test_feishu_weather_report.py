import unittest
from datetime import date

from scripts.feishu_weather_report import (
    build_payload_from_forecast,
    weather_to_cn_icon,
)

class FeishuWeatherReportTests(unittest.TestCase):
    def test_weather_mapping(self):
        self.assertEqual(weather_to_cn_icon(weather_code=95), ("雷", "⛈️"))
        self.assertEqual(weather_to_cn_icon(weather_code=65), ("大雨", "🌧️🌧️🌧️"))
        self.assertEqual(weather_to_cn_icon(weather_id=800), ("晴", "☀️"))
        self.assertEqual(weather_to_cn_icon(description="fog and haze"), ("雾霾", "🌫️"))

    def test_payload_structure_and_template(self):
        short_day = {
            "date": "2026-02-22",
            "t_min": 10,
            "t_max": 18,
            "dominant_weather_code": 0,
            "holiday": "春节",
            "key_hours": [
                {"time": "2026-02-22T09:00", "temperature": 12, "weather_code": 0, "weather_description": "Clear sky"},
                {"time": "2026-02-22T15:00", "temperature": 17, "weather_code": 2, "weather_description": "Partly cloudy"},
                {"time": "2026-02-22T21:00", "temperature": 13, "weather_code": 3, "weather_description": "Overcast"},
            ],
        }

        long_days = [
            {"date": "2026-02-23", "t_min": 7, "t_max": 16, "dominant_weather_code": 2, "holiday": "平日"},
            {"date": "2026-02-24", "t_min": 10, "t_max": 24, "dominant_weather_code": 61, "holiday": "平日"},
            {"date": "2026-02-25", "t_min": 6, "t_max": 14, "dominant_weather_code": 63, "holiday": "平日"},
            {"date": "2026-02-26", "t_min": 5, "t_max": 10, "dominant_weather_code": 65, "holiday": "平日"},
            {"date": "2026-02-27", "t_min": 2, "t_max": 7, "dominant_weather_code": 45, "holiday": "平日"},
            {"date": "2026-02-28", "t_min": 0, "t_max": 6, "dominant_weather_code": 71, "holiday": "平日"},
        ]

        forecast_result = {
            "forecast_short_open_weather": {"days": [short_day]},
            "forecast_long_open_meteo": {"days": long_days},
            "errors": [],
        }

        payload = build_payload_from_forecast(
            forecast_result=forecast_result,
            city="Beijing",
            source_cn="OpenWeather + Open-Meteo",
            updated_at_cn="2026-02-21 16:30:00",
            include_holiday=True,
            today_utc8=date(2026, 2, 21),
        )

        self.assertEqual(payload["message_type"], "text")
        self.assertEqual(payload["city"], "Beijing")
        self.assertIn("report_lines", payload)
        self.assertEqual(len(payload["days"]), 7)
        self.assertIn("**明日分时详情**", payload["report_text"])
        self.assertNotIn("**天气预报**", payload["report_text"])
        self.assertIn("**未来 7 天趋势预览**", payload["report_text"])
        self.assertIn("- 早晨（09:00） 12°C | 晴", payload["report_text"])
        self.assertIn("02-22 星期日 春节 ☀️ 10°C ～ 18°C 晴", payload["report_text"])
        self.assertIn("02-24 星期二 平日 🌧️ 10°C ～ 24°C 小雨 ⏫ ⚠️", payload["report_text"])
        self.assertIn("02-25 星期三 平日 🌧️🌧️ 6°C ～ 14°C 中雨 ⏬", payload["report_text"])
        self.assertIn("02-26 星期四 平日 🌧️🌧️🌧️ 5°C ～ 10°C 大雨 📉", payload["report_text"])
        self.assertNotIn("**图例**", payload["report_text"])
        self.assertIn("⏫ / ⏬ → T vs T-1", payload["report_text"])
        self.assertIn("📈 / 📉 → 最近几天已经形成趋势", payload["report_text"])
        self.assertIn("⚠️ → 昼夜温差大", payload["report_text"])
        self.assertNotIn("数据来源：", payload["report_text"])
        self.assertIn("更新于：2026-02-21 16:30:00（UTC+8）", payload["report_text"])
        self.assertEqual(payload["days"][0]["weekday"], "星期日")
        self.assertEqual(payload["days"][0]["alerts"], [])
        self.assertEqual(payload["days"][2]["alerts"], ["⏫", "⚠️"])


if __name__ == "__main__":
    unittest.main()
