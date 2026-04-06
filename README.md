# Weather Forecast Fusion（个人版）

这个项目用于生成固定格式的天气预报，并通过飞书流程 Webhook 发送。

核心能力：
- OpenWeather + Open-Meteo 融合天气（D+1 ~ D+7）
- 固定模板天气文本渲染
- 飞书流程触发器 JSON 推送（`message_type: "text"`）
- 支持单次执行（由宿主机 cron 负责定时触发）
- 支持节假日缓存读取并注入天气文案

## 目录说明

- `scripts/feishu_weather_report.py`：主入口（推送飞书）
- `scripts/fused_weather.py`：融合天气调试入口（输出 JSON）
- `scripts/weather_query.py`：OpenWeather 查询工具
- `scripts/holiday_fetch.py`：下载并更新节假日缓存
- `config/fusion_config.yaml`：主配置文件
- `.env`：环境变量（API Key、覆盖项）
- `.cache/holidays_cache.txt`：节假日缓存（本地）

## 运行环境

- Python 3.9+
- 需要可访问 OpenWeather / Open-Meteo 网络
- `OPENWEATHER_API_KEY` 必填

## 参数传递优先级（重点）

### 1) `feishu_weather_report.py`

优先级从高到低：
1. CLI 参数（仅 `--config`、模式参数）
2. 环境变量（如 `FEISHU_WEBHOOK_URL`）
3. `config/fusion_config.yaml` 的 `report.*`
4. 代码默认值

字段级覆盖：
- `city`：`WEATHER_REPORT_CITY` > `report.city`
- `webhook_url`：`FEISHU_WEBHOOK_URL` > `report.webhook.url`
- `weather_source_mode`：若未设置 `WEATHER_SOURCE_MODE`，会读取 `report.defaults.weather_source_mode`

### 2) `fused_weather.py`

优先级从高到低：
1. CLI 参数（`--region/--lat/--lon/--start-date/--end-date/--timezone/--include-holiday`）
2. 环境变量 `WEATHER_SOURCE_MODE`
3. `config/fusion_config.yaml` 的 `providers.weather_source_mode`
4. 默认 `open_meteo_all`

### 3) Provider 超时配置

- OpenWeather 超时：`OPENWEATHER_TIMEOUT_SECONDS`（`.env`/环境变量）
- Open-Meteo 超时：`OPENMETEO_TIMEOUT_SECONDS`（`.env`/环境变量）

### 4) 节假日缓存文件

- `HOLIDAY_CACHE_FILE` > 默认路径
- 你当前 `.env` 已配置：`HOLIDAY_CACHE_FILE=.cache/holidays_cache.txt`

## 配置文件详解（`config/fusion_config.yaml`）

```yaml
timezone: Asia/Shanghai
providers:
  weather_source_mode: open_meteo_all

report:
  city: Beijing
  timezone: Asia/Shanghai
  include_holiday: true
  source_cn: OpenWeather + Open-Meteo
  updated_at_format: "%Y-%m-%d %H:%M:%S"
  webhook:
    url: ""
    timeout_seconds: 10
    max_retries: 2
    retry_backoff_seconds: 1.5
  defaults:
    weather_source_mode: open_meteo_all
```

字段说明：
- `report.city`：默认城市（可被 `WEATHER_REPORT_CITY` 覆盖）
- `report.timezone`：天气查询和时间格式使用时区
- `report.include_holiday`：是否附加节假日
- `report.source_cn`：报告中的“数据来源”文本
- `report.updated_at_format`：`strftime` 格式（建议不带 `%z`，文案会统一标注 `UTC+8`）
- `report.webhook.url`：飞书流程 webhook 地址
- `report.webhook.timeout_seconds`：单次请求超时
- `report.webhook.max_retries`：失败重试次数（不含首发）
- `report.webhook.retry_backoff_seconds`：重试退避基础秒数

## 环境变量说明（`.env`）

当前主要变量：

- `OPENWEATHER_API_KEY`：必填
- `OPENWEATHER_TIMEOUT_SECONDS`：可选
- `OPENMETEO_TIMEOUT_SECONDS`：可选
- `HOLIDAY_CACHE_FILE`：可选
- `FEISHU_WEBHOOK_URL`：可选，覆盖配置文件 webhook
- `WEATHER_REPORT_CITY`：可选，覆盖配置文件城市
- `WEATHER_SOURCE_MODE`：可选，支持 `open_meteo_all` / `hybrid`

## 使用方式

## 1. 单次运行（只预览 payload，不发送）

```bash
python3 scripts/feishu_weather_report.py --once --dry-run --config config/fusion_config.yaml
```

用途：调试模板、字段、图标映射。

## 2. 单次运行并发送飞书

先配置 `report.webhook.url` 或 `FEISHU_WEBHOOK_URL`，然后：

```bash
python3 scripts/feishu_weather_report.py --once --config config/fusion_config.yaml
```

## 3. 输出调试信息（融合数据 + payload）

```bash
python3 scripts/feishu_weather_report.py --once --dry-run --json-debug
```

## 主入口参数表（`scripts/feishu_weather_report.py`）

| 参数           | 类型   | 说明                                           |
| -------------- | ------ | ---------------------------------------------- |
| `--config`     | string | 配置文件路径，默认 `config/fusion_config.yaml` |
| `--once`       | flag   | 立即执行一次                                   |
| `--dry-run`    | flag   | 仅打印 payload，不发送 webhook                 |
| `--json-debug` | flag   | 输出融合结果和 payload 详情                    |

不传 `--once` 也会执行一次（默认单次模式）。

## 输出 payload 结构（飞书流程触发器）

发送 JSON 顶层字段：

```json
{
  "message_type": "text",
  "report_text": "完整天气文本",
  "report_lines": ["按行拆分后的文本，便于流程节点逐行处理"],
  "city": "Beijing",
  "updated_at_cn": "2026-02-21 16:30:00",
  "source_cn": "OpenWeather + Open-Meteo",
  "days": [
    {
      "date": "02-22",
      "date_iso": "2026-02-22",
      "weekday": "星期日",
      "holiday": "",
      "min": 2,
      "max": 9,
      "weather_cn": "多云",
      "icon": "⛅",
      "alerts": ["⏫", "⚠️"]
    }
  ],
  "has_partial_data": false,
  "errors": []
}
```

当前模板约定：
- 报告从 `明日分时详情` 开始，不包含“天气预报”标题
- 明日分时固定显示时间：`09:00 / 15:00 / 21:00`
- 温度统一四舍五入为整数
- 星期使用中文（如 `星期一`）
- 更新时间显示为 `YYYY-MM-DD HH:MM:SS`，并在文案中附加 `（UTC+8）`
- 每日趋势行可能附加温度提醒符号：`⏫ ⏬ ⚠️ 📈 📉`
- 文末自动追加三行图例（无标题）：
  `⏫ / ⏬ → T vs T-1`
  `📈 / 📉 → 最近几天已经形成趋势`
  `⚠️ → 昼夜温差大`
- 符号判定规则：
  `⏫ / ⏬`：今天最高温相对昨天变化绝对值 ≥ 5°C
  `⚠️`：今天昼夜温差（最高-最低）≥ 15°C
  `📈 / 📉`：近 3 天已形成趋势（I=0.6*Tmax+0.4*Tmin，最近三段日变化同向天数≥2，且今天相对3天前 ΔI 绝对值≥4）

## 融合天气调试脚本（`scripts/fused_weather.py`）

```bash
python3 scripts/fused_weather.py --region Beijing --json-only
```

参数：

| 参数                | 类型       | 说明                          |
| ------------------- | ---------- | ----------------------------- |
| `--region`          | string     | 地区名（如 `Beijing`）        |
| `--lat`             | float      | 纬度（需与 `--lon` 同时提供） |
| `--lon`             | float      | 经度（需与 `--lat` 同时提供） |
| `--start-date`      | YYYY-MM-DD | 起始日期（限制 D+1~D+7）      |
| `--end-date`        | YYYY-MM-DD | 结束日期（限制 D+1~D+7）      |
| `--timezone`        | string     | 时区，默认 `Asia/Shanghai`    |
| `--include-holiday` | flag       | 附加节假日                    |
| `--json-only`       | flag       | 仅输出 JSON                   |

## OpenWeather 查询脚本（`scripts/weather_query.py`）

### 当前天气
```bash
python3 scripts/weather_query.py --region Beijing --json-only
```

### 某一时刻历史天气
```bash
python3 scripts/weather_query.py --region Beijing --time "2026-02-20 09:00:00" --json-only
```

### 时间区间聚合
```bash
python3 scripts/weather_query.py --region Beijing --start-time "2026-02-18" --end-time "2026-02-20" --json-only
```

参数：

| 参数           | 类型       | 说明                                      |
| -------------- | ---------- | ----------------------------------------- |
| `--region`     | string     | 地区名                                    |
| `--lat`        | float      | 纬度                                      |
| `--lon`        | float      | 经度                                      |
| `--time`       | string/int | 单时间查询（epoch 或日期时间）            |
| `--start-time` | string/int | 区间开始                                  |
| `--end-time`   | string/int | 区间结束                                  |
| `--units`      | string     | `standard/metric/imperial`，默认 `metric` |
| `--lang`       | string     | 语言，默认 `zh_cn`                        |
| `--json-only`  | flag       | 仅输出 JSON                               |

注意：
- `time` 与 `start-time/end-time` 不能同时传
- `start-time` 和 `end-time` 必须成对出现

## 节假日缓存脚本（`scripts/holiday_fetch.py`）

更新本地节假日缓存：

```bash
python3 scripts/holiday_fetch.py
```

缓存写入位置：
- `HOLIDAY_CACHE_FILE` 指定路径
- 未指定则写默认路径

## 常用实战命令

### A. 本地调通（推荐顺序）

```bash
# 1) 更新节假日缓存
python3 scripts/holiday_fetch.py

# 2) 预览飞书 payload
python3 scripts/feishu_weather_report.py --once --dry-run --json-debug

# 3) 真正发送
python3 scripts/feishu_weather_report.py --once
```

### B. 在宿主机设定 cron 推送

```bash
# 每天 23:00 执行一次（示例）
0 15 * * * /usr/bin/python3 /home/to/path/feishu-weather-forecast/scripts/feishu_weather_report.py --once --config /home/to/path/feishu-weather-forecast/config/fusion_config.yaml >> /home/to/path/feishu-weather-forecast/cron.log 2>&1
```

## 返回码约定

- `0`：成功
- 非 `0`：失败（常见原因：API Key 缺失、网络不可达、webhook 配置为空、上游无数据）
