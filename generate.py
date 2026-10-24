"""Builds dash.png (1072x1448, 8-bit grayscale) for a Kindle Paperwhite 10th gen.

Stage 2: weather + calendar. The to-do section is still a placeholder.
The calendar link is read from the CALENDAR_URL environment variable
(a GitHub secret) and is never printed or saved.
"""
import json
import os
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---- Settings you can change ----
LAT, LON = 41.3165, -73.0932        # Shelton, CT
TZ = "America/New_York"
OUT = "dash.png"
W, H = 1072, 1448
MAX_EVENTS = 5          # how many upcoming events to show
LOOKAHEAD_DAYS = 30     # how far ahead to look
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


# ---------------- weather ----------------
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


# ---------------- calendar ----------------
def load_calendar_text():
    """Returns raw .ics text, or None. Never prints the link."""
    local = os.environ.get("CALENDAR_FILE")  # for testing only
    if local:
        with open(local, "rb") as f:
            return f.read()
    link = os.environ.get("CALENDAR_URL", "").strip()
    if not link:
        return None
    if link.startswith("webcal://"):
        link = "https://" + link[len("webcal://"):]
    req = urllib.request.Request(link, headers={"User-Agent": "kindle-dashboard"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def _to_local(dt, tz):
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    return dt  # a plain date (all-day event)


def get_events(now):
    """Returns the next MAX_EVENTS upcoming events as (day, time, title) rows."""
    import icalendar
    import recurring_ical_events

    raw = load_calendar_text()
    if raw is None:
        return None
    tz = now.tzinfo
    today = now.date()
    cal = icalendar.Calendar.from_ical(raw)
    day0 = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    found = recurring_ical_events.of(cal).between(day0, day0 + timedelta(days=LOOKAHEAD_DAYS))

    rows = []
    for ev in found:
        title = str(ev.get("SUMMARY", "(no title)"))
        start = _to_local(ev.get("DTSTART").dt, tz)
        end_prop = ev.get("DTEND")
        end = _to_local(end_prop.dt, tz) if end_prop else start

        if isinstance(start, datetime):
            if end <= now:
                continue  # already finished
            show_day = start.date()
            if show_day < today:
                show_day = today  # started earlier and still running
            time_label = start.strftime("%-I:%M%p").lower()
            order = (show_day, 1, start)
        else:  # all-day (DTEND is exclusive)
            last = (end - timedelta(days=1)) if (isinstance(end, date) and not isinstance(end, datetime)) else start
            if last < today:
                continue
            show_day = max(start, today)
            time_label = "All day"
            order = (show_day, 0, datetime.combine(show_day, datetime.min.time(), tzinfo=tz))

        if show_day == today:
            day_label = "Today"
        elif show_day == today + timedelta(days=1):
            day_label = "Tmrw"
        else:
            day_label = datetime.combine(show_day, datetime.min.time()).strftime("%a %-m/%-d")
        rows.append((order, day_label, time_label, title))

    rows.sort(key=lambda r: r[0])
    return [(d, t, title) for _, d, t, title in rows[:MAX_EVENTS]]


def fit(text, fnt, max_w, draw):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "\u2026", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "\u2026"


# ---------------- drawing ----------------
def render(data, events, now):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = 50

    # Header
    d.text((pad, 40), now.strftime("%A"), font=font(84, True), fill=0)
    d.text((pad, 140), now.strftime("%B %-d, %Y"), font=font(46), fill=40)
    d.line([pad, 215, W - pad, 215], fill=0, width=5)

    # Current weather
    if data:
        cur = data["current"]
        d.text((pad, 235), f"{round(cur['temperature_2m'])}\u00b0", font=font(190, True), fill=0)
        d.text((pad + 400, 270), WMO.get(cur["weather_code"], ""), font=font(60, True), fill=0)
        d.text((pad + 400, 350), f"Feels like {round(cur['apparent_temperature'])}\u00b0", font=font(42), fill=40)
        d.text((pad + 400, 410), f"Wind {round(cur['wind_speed_10m'])} mph", font=font(42), fill=40)
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
            pop = daily["precipitation_probability_max"][i]
            code = WMO.get(daily["weather_code"][i], "")
            d.text((x, 525), day, font=font(40, True), fill=0)
            d.text((x, 580), f"{round(daily['temperature_2m_max'][i])}\u00b0", font=font(52, True), fill=0)
            d.text((x, 645), f"{round(daily['temperature_2m_min'][i])}\u00b0", font=font(40), fill=70)
            d.text((x, 700), f"{pop}%" if pop is not None else "", font=font(32), fill=70)
            d.text((x, 745), code.split()[0] if code else "", font=font(28), fill=70)

    d.line([pad, 810, W - pad, 810], fill=0, width=5)

    # Calendar: next upcoming events
    d.text((pad, 828), "UPCOMING", font=font(44, True), fill=0)
    y = 892
    row_h = 52
    if events is None:
        d.text((pad, y), "Calendar not set up", font=font(38), fill=110)
    elif not events:
        d.text((pad, y), "No upcoming events", font=font(38), fill=110)
    else:
        x_day, x_time, x_title = pad, pad + 170, pad + 340
        for day_label, time_label, title in events:
            d.text((x_day, y), day_label, font=font(32, True), fill=0)
            d.text((x_time, y), time_label, font=font(32), fill=40)
            d.text((x_title, y), fit(title, font(34), W - pad - x_title, d), font=font(34), fill=0)
            y += row_h

    d.line([pad, 1180, W - pad, 1180], fill=0, width=5)

    # To-do placeholder
    d.text((pad, 1198), "TO DO", font=font(44, True), fill=0)
    d.text((pad, 1268), "Reminders coming soon", font=font(38), fill=110)

    # Footer
    d.text((W - pad, H - 40), f"Updated {now.strftime('%-I:%M %p')}",
           font=font(28), fill=110, anchor="rs")
    return img


def main():
    now = datetime.now(ZoneInfo(TZ))
    try:
        data = fetch_weather()
    except Exception as e:
        print("Weather fetch failed:", type(e).__name__)
        data = None
    try:
        events = get_events(now)
    except Exception as e:
        # Print only the error type: messages can contain the private link.
        print("Calendar fetch failed:", type(e).__name__)
        events = None
    render(data, events, now).save(OUT)
    print("Saved", OUT)


if __name__ == "__main__":
    main()
