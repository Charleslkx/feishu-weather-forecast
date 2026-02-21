# Weather API Documentation

The API endpoint /v1/cma accepts a geographical coordinate, a list of weather variables and responds with a JSON hourly weather forecast for 7 days. Time always starts at 0:00 today and contains 168 hours. If &forecast_days=16 is set, up to 10 days of forecast can be returned. All URL parameters are listed below:

| Parameter | Format | Required | Default | Description |
| --- | --- | --- | --- | --- |
| latitude, longitude | Floating point | Yes |  | Geographical WGS84 coordinates of the location. Multiple coordinates can be comma separated. E.g. &latitude=52.52,48.85&longitude=13.41,2.35. To return data for multiple locations the JSON output changes to a list of structures. CSV and XLSX formats add a column location_id. |
| elevation | Floating point | No |  | The elevation used for statistical downscaling. Per default, a 90 meter digital elevation model is used. You can manually set the elevation to correctly match mountain peaks. If &elevation=nan is specified, downscaling will be disabled and the API uses the average grid-cell height. |
| hourly | String array | No |  | A list of weather variables which should be returned. Values can be comma separated, or multiple &hourly= parameter in the URL can be used. |
| daily | String array | No |  | A list of daily weather variable aggregations which should be returned. Values can be comma separated, or multiple &daily= parameter in the URL can be used. If daily weather variables are specified, parameter timezone is required. |
| temperature_unit | String | No | celsius | If fahrenheit is set, all temperature values are converted to Fahrenheit. |
| wind_speed_unit | String | No | kmh | Other wind speed speed units: ms, mph and kn |
| precipitation_unit | String | No | mm | Other precipitation amount units: inch |
| timeformat | String | No | iso8601 | If format unixtime is selected, all time values are returned in UNIX epoch time in seconds. Please note that all timestamp are in GMT+0! For daily values with unix timestamps, please apply utc_offset_seconds again to get the correct date. |
| timezone | String | No | GMT | If timezone is set, all timestamps are returned as local-time and data is returned starting at 00:00 local-time. Any time zone name from the time zone database is supported. If auto is set as a time zone, the coordinates will be automatically resolved to the local time zone. For multiple coordinates, a comma separated list of timezones can be specified. |
| past_days | Integer | No | 0 | If past_days is set, past weather data can be returned. |
| forecast_days | Integer (0-16) | No | 7 | Per default, only 7 days are returned. Up to 16 days of forecast are possible. |
| forecast_hours<br>past_hours | Integer (>0) | No |  | Similar to forecast_days, the number of timesteps of hourly data can controlled. Instead of using the current day as a reference, the current hour is used. |
| start_date<br>end_date | String (yyyy-mm-dd) | No |  | The time interval to get weather data. A day must be specified as an ISO8601 date (e.g. 2022-06-30). |
| start_hour<br>end_hour | String (yyyy-mm-ddThh:mm) | No |  | The time interval to get weather data for hourly. Time must be specified as an ISO8601 date (e.g. 2022-06-30T12:00). |
| cell_selection | String | No | land | Set a preference how grid-cells are selected. The default land finds a suitable grid-cell on land with similar elevation to the requested coordinates using a 90-meter digital elevation model. sea prefers grid-cells on sea. nearest selects the nearest possible grid-cell. |
| apikey | String | No |  | Only required to commercial use to access reserved API resources for customers. The server URL requires the prefix customer-. See pricing for more information. |

Additional optional URL parameters will be added. For API stability, no required parameters will be added in the future!

## Hourly Parameter Definition

The parameter &hourly= accepts the following values. Most weather variables are given as an instantaneous value for the indicated hour. Some variables like precipitation are calculated from the preceding hour as an average or sum.

| Variable | Valid time | Unit | Description |
| --- | --- | --- | --- |
| temperature_2m | Instant | °C (°F) | Air temperature at 2 meters above ground |
| relative_humidity_2m | Instant | % | Relative humidity at 2 meters above ground |
| dew_point_2m | Instant | °C (°F) | Dew point temperature at 2 meters above ground |
| apparent_temperature | Instant | °C (°F) | Apparent temperature is the perceived feels-like temperature combining wind chill factor, relative humidity and solar radiation |
| pressure_msl<br>surface_pressure | Instant | hPa | Atmospheric air pressure reduced to mean sea level (msl) or pressure at surface. Typically pressure on mean sea level is used in meteorology. Surface pressure gets lower with increasing elevation. |
| cloud_cover | Instant | % | Total cloud cover as an area fraction |
| cloud_cover_low | Instant | % | Low level clouds and fog up to 3 km altitude |
| cloud_cover_mid | Instant | % | Mid level clouds from 3 to 8 km altitude |
| cloud_cover_high | Instant | % | High level clouds from 8 km altitude |
| wind_speed_10m<br>wind_speed_30m<br>wind_speed_50m<br>wind_speed_70m<br>wind_speed_100m<br>wind_speed_120m<br>wind_speed_140m<br>wind_speed_160m<br>wind_speed_180m<br>wind_speed_200m | Instant | km/h (mph, m/s, knots) | Wind speed at 10, 30, 50, 70, 100, 120, 140, 160, 180 or 200 meters above ground. Wind speed on 10 meters is the standard level. |
| wind_direction_10m<br>wind_direction_30m<br>wind_direction_50m<br>wind_direction_70m<br>wind_direction_100m<br>wind_direction_120m<br>wind_direction_140m<br>wind_direction_160m<br>wind_direction_180m<br>wind_direction_200m | Instant | ° | Wind direction at 10, 30, 50, 70, 100, 120, 140, 160, 180 or 200 meters above ground |
| wind_gusts_10m | Preceding hour max | km/h (mph, m/s, knots) | Gusts at 10 meters above ground as a maximum of the preceding hour |
| shortwave_radiation | Preceding hour mean | W/m² | Shortwave solar radiation as average of the preceding hour. This is equal to the total global horizontal irradiation |
| direct_radiation<br>direct_normal_irradiance | Preceding hour mean | W/m² | Direct solar radiation as average of the preceding hour on the horizontal plane and the normal plane (perpendicular to the sun). GRAPES does bot offers direct radiation directly. It is approximated based on Razo, Müller Witwer |
| diffuse_radiation | Preceding hour mean | W/m² | Diffuse solar radiation as average of the preceding hour. HRRR offers diffuse radiation directly. GRAPES does bot offers diffuse radiation directly. It is approximated based on Razo, Müller Witwer |
| global_tilted_irradiance | Preceding hour mean | W/m² | Total radiation received on a tilted pane as average of the preceding hour. The calculation is assuming a fixed albedo of 20% and in isotropic sky. Please specify tilt and azimuth parameter. Tilt ranges from 0° to 90° and is typically around 45°. Azimuth should be close to 0° (0° south, -90° east, 90° west, ±180 north). If azimuth is set to "nan", the calculation assumes a vertical tracker (east-west). If tilt is set to "nan", it is assumed that the panel has a horizontal tracker (up-down). If both are set to "nan", a bi-axial tracker is assumed. |
| sunshine_duration | Preceding hour sum | Seconds | Number of seconds of sunshine of the preceding hour per hour calculated by direct normalized irradiance exceeding 120 W/m², following the WMO definition. |
| vapour_pressure_deficit | Instant | kPa | Vapor Pressure Deificit (VPD) in kilopascal (kPa). For high VPD (>1.6), water transpiration of plants increases. For low VPD (<0.4), transpiration decreases |
| et0_fao_evapotranspiration | Preceding hour sum | mm (inch) | ET₀ Reference Evapotranspiration of a well watered grass field. Based on FAO-56 Penman-Monteith equations ET₀ is calculated from temperature, wind speed, humidity and solar radiation. Unlimited soil water is assumed. ET₀ is commonly used to estimate the required irrigation for plants. |
| weather_code | Instant | WMO code | Weather condition as a numeric code. Follow WMO weather interpretation codes. See table below for details. Weather code is calculated from cloud cover analysis, precipitation, snowfall, cape, lifted index and gusts. |
| precipitation | Preceding hour sum | mm (inch) | Total precipitation (rain, showers, snow) sum of the preceding hour |
| snowfall | Preceding hour sum | cm (inch) | Snowfall amount of the preceding hour in centimeters. For the water equivalent in millimeter, divide by 7. E.g. 7 cm snow = 10 mm precipitation water equivalent |
| rain | Preceding hour sum | mm (inch) | Rain from large scale weather systems of the preceding hour in millimeter |
| showers | Preceding hour sum | mm (inch) | Showers from convective precipitation in millimeters from the preceding hour |
| snow_depth | Instant | meters | Snow depth on the ground |
| visibility | Instant | meters | Viewing distance in meters. Influenced by low clouds, humidity and aerosols. |
| cape | Instant | J/kg | Convective available potential energy. See Wikipedia. |
| lifted_index | Instant | dimensionless | Atmospheric stability. See Wikipedia. |
| soil_temperature_0_to_10cm<br>soil_temperature_10_to_40cm<br>soil_temperature_40_to_100cm<br>soil_temperature_100_to_200cm | Instant | °C (°F) | Temperature in the soil as an average on 0-10, 10-40, 40-100 and 100-200 cm depths. |
| soil_moisture_0_to_10cm<br>soil_moisture_10_to_40cm<br>soil_moisture_40_to_100cm<br>soil_moisture_100_to_200cm | Instant | m³/m³ | Average soil water content as volumetric mixing ratio at 0-10, 10-40, 40-100 and 100-200 cm depths. |

## Pressure Level Variables

Pressure level variables do not have fixed altitudes. Altitude varies with atmospheric pressure. 1000 hPa is roughly between 60 and 160 meters above sea level. Estimated altitudes are given below. Altitudes are in meters above sea level (not above ground). For precise altitudes, geopotential_height can be used.

| Level (hPa) | 1000 | 975 | 950 | 925 | 900 | 850 | 800 | 750 | 700 | 650 | 600 | 550 | 500 | 450 | 400 | 350 | 300 | 275 | 250 | 225 | 200 | 175 | 150 | 125 | 100 | 70 | 50 | 30 | 20 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Altitude | 110 m | 320 m | 500 m | 800 m | 1000 m | 1500 m | 1900 m | 2.5 km | 3 km | 3.6 km | 4.2 km | 4.9 km | 5.6 km | 6.3 km | 7.2 km | 8.1 km | 9.2 km | 9.7 km | 10.4 km | 11 km | 11.8 km | 12.6 km | 13.5 km | 14.6 km | 15.8 km | 17.7 km | 19.3 km | 22 km | 23 km | 26 km |

All pressure levels have valid times of the indicated hour (instant).

| Variable | Unit | Description |
| --- | --- | --- |
| weather_code | WMO code | The most severe weather condition on a given day |
| temperature_1000hPa<br>temperature_975hPa, ... | °C (°F) | Air temperature at the specified pressure level. Air temperatures decrease linearly with pressure. |
| relative_humidity_1000hPa<br>relative_humidity_975hPa, ... | % | Relative humidity at the specified pressure level. |
| dew_point_1000hPa<br>dew_point_975hPa, ... | °C (°F) | Dew point temperature at the specified pressure level. |
| cloud_cover_1000hPa<br>cloud_cover_975hPa, ... | % | Cloud cover at the specified pressure level. |
| wind_speed_1000hPa<br>wind_speed_975hPa, ... | km/h (mph, m/s, knots) | Wind speed at the specified pressure level. |
| wind_direction_1000hPa<br>wind_direction_975hPa, ... | ° | Wind direction at the specified pressure level. |
| geopotential_height_1000hPa<br>geopotential_height_975hPa, ... | meter | Geopotential height at the specified pressure level. This can be used to get the correct altitude in meter above sea level of each pressure level. Be carefull not to mistake it with altitude above ground. |

## Daily Parameter Definition

Aggregations are a simple 24 hour aggregation from hourly values. The parameter &daily= accepts the following values:

| Variable | Unit | Description |
| --- | --- | --- |
| temperature_2m_max<br>temperature_2m_min | °C (°F) | Maximum and minimum daily air temperature at 2 meters above ground |
| apparent_temperature_max<br>apparent_temperature_min | °C (°F) | Maximum and minimum daily apparent temperature |
| precipitation_sum | mm | Sum of daily precipitation (including rain, showers and snowfall) |
| snowfall_sum | cm | Sum of daily snowfall |
| precipitation_hours | hours | The number of hours with rain |
| sunrise<br>sunset | iso8601 | Sun rise and set times |
| sunshine_duration | seconds | The number of seconds of sunshine per day is determined by calculating direct normalized irradiance exceeding 120 W/m², following the WMO definition. Sunshine duration will consistently be less than daylight duration due to dawn and dusk. |
| daylight_duration | seconds | Number of seconds of daylight per day |
| wind_speed_10m_max<br>wind_gusts_10m_max | km/h (mph, m/s, knots) | Maximum wind speed and gusts on a day |
| wind_direction_10m_dominant | ° | Dominant wind direction |
| shortwave_radiation_sum | MJ/m² | The sum of solar radiation on a given day in Megajoules |
| et0_fao_evapotranspiration | mm | Daily sum of ET₀ Reference Evapotranspiration of a well watered grass field |

## JSON Return Object

On success a JSON object will be returned.

```json
{
    "latitude": 52.52,
    "longitude": 13.419,
    "elevation": 44.812,
    "generationtime_ms": 2.2119,
    "utc_offset_seconds": 0,
    "timezone": "Europe/Berlin",
    "timezone_abbreviation": "CEST",
    "hourly": {
        "time": ["2022-07-01T00:00", "2022-07-01T01:00", "2022-07-01T02:00", ...],
        "temperature_2m": [13, 12.7, 12.7, 12.5, 12.5, 12.8, 13, 12.9, 13.3, ...]
    },
    "hourly_units": {
        "temperature_2m": "°C"
    }
}
```

| Parameter | Format | Description |
| --- | --- | --- |
| latitude, longitude | Floating point | WGS84 of the center of the weather grid-cell which was used to generate this forecast. This coordinate might be a few kilometres away from the requested coordinate. |
| elevation | Floating point | The elevation from a 90 meter digital elevation model. This effects which grid-cell is selected (see parameter cell_selection). Statistical downscaling is used to adapt weather conditions for this elevation. This elevation can also be controlled with the query parameter elevation. If &elevation=nan is specified, all downscaling is disabled and the averge grid-cell elevation is used. |
| generationtime_ms | Floating point | Generation time of the weather forecast in milliseconds. This is mainly used for performance monitoring and improvements. |
| utc_offset_seconds | Integer | Applied timezone offset from the &timezone= parameter. |
| timezone<br>timezone_abbreviation | String | Timezone identifier (e.g. Europe/Berlin) and abbreviation (e.g. CEST) |
| hourly | Object | For each selected weather variable, data will be returned as a floating point array. Additionally a time array will be returned with ISO8601 timestamps. |
| hourly_units | Object | For each selected weather variable, the unit will be listed here. |
| daily | Object | For each selected daily weather variable, data will be returned as a floating point array. Additionally a time array will be returned with ISO8601 timestamps. |
| daily_units | Object | For each selected daily weather variable, the unit will be listed here. |

## Errors

In case an error occurs, for example a URL parameter is not correctly specified, a JSON error object is returned with a HTTP 400 status code.

```json
{
    "error": true, 
    "reason": "Cannot initialize WeatherVariable from invalid String value
	    tempeture_2m for key hourly" 
}
```
