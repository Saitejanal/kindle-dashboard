"""Builds dash.png (1072x1448, 8-bit grayscale) for a Kindle Paperwhite 10th gen.

Stage 1: weather + date only. Calendar and to-do sections are placeholders.
"""
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---- Settings you can change ----
LAT, LON = 41.3165, -73.0932        # Shelton, CT
TZ = "America/New_York"
OUT = "dash.png"
W, H = 1072, 1448
# ---------------------------------

WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=False):
    try:
        return ImageFont.truetype(BOLD if bold else REG, size)
    except OSError:
        return ImageFont.load_default()


def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone={TZ.replace('/', '%2F')}&forecast_days=5"
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def render(data, now):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = 50

    # Header: date and time
    d.text((pad, 40), now.strftime("%A"), font=font(84, True), fill=0)
    d.text((pad, 140), now.strftime("%B %-d, %Y"), font=font(46), fill=40)
    d.line([pad, 215, W - pad, 215], fill=0, width=5)

    # Current weather
    if data:
        cur = data["current"]
        temp = round(cur["temperature_2m"])
        feels = round(cur["apparent_temperature"])
        cond = WMO.get(cur["weather_code"], "")
        wind = round(cur["wind_speed_10m"])
        d.text((pad, 235), f"{temp}\u00b0", font=font(190, True), fill=0)
        d.text((pad + 400, 270), cond, font=font(60, True), fill=0)
        d.text((pad + 400, 350), f"Feels like {feels}\u00b0", font=font(42), fill=40)
        d.text((pad + 400, 410), f"Wind {wind} mph", font=font(42), fill=40)
    else:
        d.text((pad, 270), "Weather unavailable", font=font(60, True), fill=0)

    d.line([pad, 500, W - pad, 500], fill=0, width=3)

    # 5-day forecast
    if data:
        daily = data["daily"]
        colw = (W - 2 * pad) // 5
        for i in range(5):
            x = pad + i * colw
            day = datetime.fromisoformat(daily["time"][i]).strftime("%a")
            hi = round(daily["temperature_2m_max"][i])
            lo = round(daily["temperature_2m_min"][i])
            pop = daily["precipitation_probability_max"][i]
            code = WMO.get(daily["weather_code"][i], "")
            d.text((x, 525), day, font=font(40, True), fill=0)
            d.text((x, 580), f"{hi}\u00b0", font=font(52, True), fill=0)
            d.text((x, 645), f"{lo}\u00b0", font=font(40), fill=70)
            d.text((x, 700), f"{pop}%" if pop is not None else "", font=font(32), fill=70)
            d.text((x, 745), code.split()[0] if code else "", font=font(28), fill=70)

    d.line([pad, 810, W - pad, 810], fill=0, width=5)

    # Calendar placeholder
    d.text((pad, 830), "TODAY", font=font(44, True), fill=0)
    d.text((pad, 900), "Calendar coming soon", font=font(38), fill=110)

    d.line([pad, 1090, W - pad, 1090], fill=0, width=5)

    # To-do placeholder
    d.text((pad, 1110), "TO DO", font=font(44, True), fill=0)
    d.text((pad, 1180), "Reminders coming soon", font=font(38), fill=110)

    # Footer
    d.text((W - pad, H - 40), f"Updated {now.strftime('%-I:%M %p')}",
           font=font(28), fill=110, anchor="rs")
    return img


def main():
    now = datetime.now(ZoneInfo(TZ))
    try:
        data = fetch_weather()
    except Exception as e:  # keep the dashboard alive if the API hiccups
        print("Weather fetch failed:", e)
        data = None
    render(data, now).save(OUT)
    print("Saved", OUT)


if __name__ == "__main__":
    main()
