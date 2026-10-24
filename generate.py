"""Builds dash.png (1072x1448, 8-bit grayscale) for a Kindle Paperwhite 10th gen.

Stage 3 layout: header (sunrise/sunset/moon), compact weather + air/UV, weather
alert bar (only when active), next 5 calendar events + countdown, and boxes for
HOME (Nest) and CAT (litter) that are placeholders until we connect them.

The calendar link is read from the CALENDAR_URL environment variable
(a GitHub secret) and is never printed or saved.
"""
import json
import math
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---- Settings you can change ----
LAT, LON = 41.3165, -73.0932        # Shelton, CT
TZ = "America/New_York"
OUT = "dash.png"
W, H = 1072, 1448
MAX_EVENTS = 5
LOOKAHEAD_DAYS = 90
LITTER_EVERY_DAYS = 2   # how often the litter box should be cleaned
STATE_FILE = "state.json"
# ---------------------------------

UA = {"User-Agent": "kindle-dashboard (github.com/Saitejanal/kindle-dashboard)"}

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


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------- data: weather, air, alerts ----------------
def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset,uv_index_max"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone={TZ.replace('/', '%2F')}&forecast_days=4"
    )
    return get_json(url)


def fetch_air():
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={LAT}&longitude={LON}&current=us_aqi"
        f"&timezone={TZ.replace('/', '%2F')}"
    )
    return get_json(url)["current"].get("us_aqi")


def fetch_alerts(now):
    """Active National Weather Service alerts for this point -> list of short strings."""
    data = get_json(f"https://api.weather.gov/alerts/active?point={LAT},{LON}",
                    {**UA, "Accept": "application/geo+json"})
    rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
    items = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        end = p.get("ends") or p.get("expires")
        until = ""
        if end:
            e = datetime.fromisoformat(end).astimezone(now.tzinfo)
            fmt = "%-I %p" if e.minute == 0 else "%-I:%M %p"
            day = "" if e.date() == now.date() else e.strftime("%a ")
            until = f" until {day}{e.strftime(fmt)}"
        items.append((rank.get(p.get("severity"), 4), f"{p.get('event', 'Alert')}{until}"))
    items.sort(key=lambda t: t[0])
    return [t for _, t in items]


# ---------------- moon ----------------
SYNODIC = 29.530588853
REF_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase(now):
    days = (now.astimezone(timezone.utc) - REF_NEW_MOON).total_seconds() / 86400
    return (days % SYNODIC) / SYNODIC     # 0 new, 0.5 full


def moon_name(p):
    """Names by phase fraction (0 new, 0.5 full) with sensible windows."""
    if p < 0.03 or p >= 0.97:
        return "New moon"
    if p < 0.22:
        return "Waxing crescent"
    if p < 0.28:
        return "First quarter"
    if p < 0.47:
        return "Waxing gibbous"
    if p < 0.53:
        return "Full moon"
    if p < 0.72:
        return "Waning gibbous"
    if p < 0.78:
        return "Last quarter"
    return "Waning crescent"


def draw_moon(d, cx, cy, r, p):
    theta = 2 * math.pi * p
    for dy in range(-r, r + 1):
        w = math.sqrt(max(r * r - dy * dy, 0))
        xt = w * math.cos(theta)
        d.line((cx - w, cy + dy, cx + w, cy + dy), fill=215)          # dark side (light gray)
        if p < 0.5:
            d.line((cx + xt, cy + dy, cx + w, cy + dy), fill=0)        # lit: right (black)
        else:
            d.line((cx - w, cy + dy, cx - xt, cy + dy), fill=0)        # lit: left (black)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=0, width=3)


# ---------------- calendar ----------------
def load_calendar_text():
    """Returns raw .ics bytes, or None. Never prints the link."""
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
        return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    return dt  # plain date (all-day)


def get_events(now):
    """Returns (rows, countdown_text). rows = next MAX_EVENTS as (day, time, title).
    Events titled 'Countdown: Something' feed the countdown box instead."""
    import icalendar
    import recurring_ical_events

    raw = load_calendar_text()
    if raw is None:
        return None, None
    tz = now.tzinfo
    today = now.date()
    cal = icalendar.Calendar.from_ical(raw)
    day0 = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    found = recurring_ical_events.of(cal).between(day0, day0 + timedelta(days=LOOKAHEAD_DAYS))

    rows, countdowns = [], []
    for ev in found:
        title = str(ev.get("SUMMARY", "(no title)"))
        start = _to_local(ev.get("DTSTART").dt, tz)
        end_prop = ev.get("DTEND")
        end = _to_local(end_prop.dt, tz) if end_prop else start

        if isinstance(start, datetime):
            if end <= now:
                continue
            show_day = max(start.date(), today)
            time_label = start.strftime("%-I:%M%p").lower()
            order = (show_day, 1, start)
        else:
            last = (end - timedelta(days=1)) if (isinstance(end, date) and not isinstance(end, datetime)) else start
            if last < today:
                continue
            show_day = max(start, today)
            time_label = "All day"
            order = (show_day, 0, datetime.combine(show_day, datetime.min.time(), tzinfo=tz))

        if title.lower().startswith("countdown:"):
            countdowns.append((show_day, title.split(":", 1)[1].strip()))
            continue

        if show_day == today:
            day_label = "Today"
        elif show_day == today + timedelta(days=1):
            day_label = "Tmrw"
        else:
            day_label = datetime.combine(show_day, datetime.min.time()).strftime("%a %-m/%-d")
        rows.append((order, day_label, time_label, title))

    rows.sort(key=lambda r: r[0])
    out = [(d_, t_, title) for _, d_, t_, title in rows[:MAX_EVENTS]]

    countdown = None
    if countdowns:
        countdowns.sort()
        when, name = countdowns[0]
        n = (when - today).days
        if n <= 0:
            countdown = f"{name} is today"
        elif n == 1:
            countdown = f"{name} is tomorrow"
        else:
            countdown = f"{name} in {n} days"
    return out, countdown


def fit(text, fnt, max_w, draw):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "\u2026", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "\u2026"


# ---------------- litter state ----------------
def load_litter(now):
    """Reads state.json -> dict(days, mood, headline, sub, filled) or None."""
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        last = date.fromisoformat(json.load(f)["litter_last_cleaned"])
    days = max((now.date() - last).days, 0)
    every = LITTER_EVERY_DAYS
    if days == 0:
        mood, head = "happy", "Cleaned today"
        sub = "Next in %d days" % every if every > 1 else "Due tomorrow"
    elif days < every:
        mood, head = "ok", "1 day ago" if days == 1 else f"{days} days ago"
        left = every - days
        sub = "Due tomorrow" if left == 1 else f"Due in {left} days"
    else:
        mood, head = "grumpy", f"{days} days ago"
        sub = "Due today" if days == every else "Overdue!"
    filled = min(4, round(days / every * 4))
    return {"days": days, "mood": mood, "headline": head, "sub": sub, "filled": filled}


# ---------------- the cat ----------------
def draw_cat(d, cx, cy, size, mood):
    """Tuxedo cat: black body, white blaze, muzzle, bib, front paws and hip patch.
    mood: happy | ok | grumpy"""
    s = size / 200.0
    BLK, WHT = 0, 255
    tail = [(cx+52*s, cy+108*s), (cx+92*s, cy+112*s), (cx+118*s, cy+88*s), (cx+120*s, cy+52*s), (cx+104*s, cy+30*s)]
    d.line(tail, fill=BLK, width=int(16*s), joint="curve")
    for p in (tail[0], tail[-1]):
        d.ellipse((p[0]-8*s, p[1]-8*s, p[0]+8*s, p[1]+8*s), fill=BLK)
    d.ellipse((cx-60*s, cy+2*s, cx+60*s, cy+120*s), fill=BLK)
    d.polygon([(cx-30*s, cy+22*s), (cx+30*s, cy+22*s), (cx+20*s, cy+66*s), (cx+8*s, cy+96*s),
               (cx-8*s, cy+96*s), (cx-20*s, cy+66*s)], fill=WHT)
    d.ellipse((cx+34*s, cy+72*s, cx+62*s, cy+114*s), fill=WHT)
    for sx in (-1, 1):
        x = cx + sx*17*s
        d.rounded_rectangle((x-15*s, cy+92*s, x+15*s, cy+122*s), radius=int(12*s), fill=WHT,
                            outline=BLK, width=max(2, int(3*s)))
    d.ellipse((cx-57*s, cy-74*s, cx+57*s, cy+34*s), fill=BLK)
    d.polygon([(cx-55*s, cy-38*s), (cx-52*s, cy-112*s), (cx-10*s, cy-66*s)], fill=BLK)
    d.polygon([(cx+55*s, cy-38*s), (cx+52*s, cy-112*s), (cx+10*s, cy-66*s)], fill=BLK)
    d.polygon([(cx-44*s, cy-50*s), (cx-43*s, cy-92*s), (cx-20*s, cy-65*s)], fill=70)
    d.polygon([(cx+44*s, cy-50*s), (cx+43*s, cy-92*s), (cx+20*s, cy-65*s)], fill=70)
    d.polygon([(cx-4*s, cy-66*s), (cx+4*s, cy-66*s), (cx+9*s, cy-14*s), (cx+14*s, cy+4*s),
               (cx-14*s, cy+4*s), (cx-9*s, cy-14*s)], fill=WHT)
    d.ellipse((cx-27*s, cy-4*s, cx+27*s, cy+30*s), fill=WHT)
    d.ellipse((cx-17*s, cy+16*s, cx+17*s, cy+36*s), fill=WHT)
    ex, ey, r = 28*s, -28*s, 15*s
    for sx in (-1, 1):
        x, y = cx + sx*ex, cy + ey
        if mood == "happy":
            d.arc((x-r, y-r*0.2, x+r, y+r*1.6), 200, 340, fill=WHT, width=max(3, int(5*s)))
        else:
            d.ellipse((x-r, y-r, x+r, y+r), fill=210)
            py = y + (4*s if mood == "grumpy" else 0)
            d.ellipse((x-r*0.32, py-r*0.85, x+r*0.32, py+r*0.85), fill=BLK)
        if mood == "grumpy":
            d.line((x - sx*r*1.4, y - r*2.0, x + sx*r*0.6, y - r*0.8), fill=WHT, width=max(3, int(6*s)))
    d.polygon([(cx-7*s, cy+2*s), (cx+7*s, cy+2*s), (cx, cy+12*s)], fill=60)
    mw = max(2, int(3*s))
    if mood == "happy":
        d.arc((cx-20*s, cy+8*s, cx, cy+28*s), 20, 160, fill=BLK, width=mw)
        d.arc((cx, cy+8*s, cx+20*s, cy+28*s), 20, 160, fill=BLK, width=mw)
    elif mood == "ok":
        d.line((cx, cy+12*s, cx, cy+18*s), fill=BLK, width=mw)
        d.line((cx-12*s, cy+22*s, cx, cy+18*s), fill=BLK, width=mw)
        d.line((cx+12*s, cy+22*s, cx, cy+18*s), fill=BLK, width=mw)
    else:
        d.arc((cx-14*s, cy+18*s, cx+14*s, cy+38*s), 200, 340, fill=BLK, width=mw)
    for sy in (-2, 10):
        for sx in (-1, 1):
            d.line((cx+sx*22*s, cy+sy*s, cx+sx*56*s, cy+(sy-3)*s), fill=WHT, width=max(1, int(2*s)))
            d.line((cx+sx*56*s, cy+(sy-3)*s, cx+sx*94*s, cy+(sy-9)*s), fill=BLK, width=max(1, int(3*s)))
    if mood == "grumpy":
        for dx, dy in ((80, -92), (100, -72)):
            x, y = cx + dx*s, cy + dy*s
            d.line((x-10*s, y, x+10*s, y), fill=BLK, width=int(5*s))
            d.line((x, y-10*s, x, y+10*s), fill=BLK, width=int(5*s))


# ---------------- drawing ----------------
def fmt_clock(iso):
    return datetime.fromisoformat(iso).strftime("%-I:%M %p")


def render(ctx):
    now = ctx["now"]
    wx, aqi, alerts = ctx["weather"], ctx["aqi"], ctx["alerts"]
    events, countdown = ctx["events"]
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = 44

    # --- header ---
    d.text((pad, 24), now.strftime("%A"), font=font(76, True), fill=0)
    d.text((pad, 114), now.strftime("%B %-d, %Y"), font=font(38), fill=40)
    p = moon_phase(now)
    if wx:
        d.text((W-pad, 34), f"Sunrise {fmt_clock(wx['daily']['sunrise'][0])}", font=font(28), fill=0, anchor="ra")
        d.text((W-pad, 72), f"Sunset {fmt_clock(wx['daily']['sunset'][0])}", font=font(28), fill=0, anchor="ra")
    name = moon_name(p)
    tw = d.textlength(name, font=font(24))
    d.text((W-pad, 124), name, font=font(24), fill=70, anchor="ra")
    draw_moon(d, int(W-pad-tw-26), 138, 16, p)
    d.line([pad, 175, W-pad, 175], fill=0, width=5)

    # --- weather ---
    if wx:
        cur, daily = wx["current"], wx["daily"]
        d.text((pad, 190), f"{round(cur['temperature_2m'])}\u00b0", font=font(140, True), fill=0)
        d.text((pad+290, 205), WMO.get(cur["weather_code"], ""), font=font(36, True), fill=0)
        d.text((pad+290, 255), f"Feels {round(cur['apparent_temperature'])}\u00b0 \u00b7 {round(cur['wind_speed_10m'])} mph",
               font=font(26), fill=40)
        bits = []
        if aqi is not None:
            bits.append(f"Air {round(aqi)}")
        uv = daily.get("uv_index_max", [None])[0]
        if uv is not None:
            bits.append(f"UV {round(uv)}")
        if bits:
            d.text((pad+290, 293), " \u00b7 ".join(bits), font=font(26), fill=40)
        x0, cw = 640, 130
        for i in range(3):
            j = i + 1
            x = x0 + i*cw
            pop = daily["precipitation_probability_max"][j]
            d.text((x, 195), datetime.fromisoformat(daily["time"][j]).strftime("%a"), font=font(28, True), fill=0)
            d.text((x, 235), f"{round(daily['temperature_2m_max'][j])}\u00b0", font=font(42, True), fill=0)
            d.text((x, 290), f"{round(daily['temperature_2m_min'][j])}\u00b0", font=font(30), fill=80)
            d.text((x, 332), f"{pop}%" if pop is not None else "", font=font(24), fill=80)
    else:
        d.text((pad, 250), "Weather unavailable", font=font(50, True), fill=0)
    d.line([pad, 375, W-pad, 375], fill=0, width=3)

    # --- alert bar (only when there is an active alert) ---
    dy = -70
    if alerts:
        dy = 0
        d.rectangle((pad, 392, W-pad, 446), fill=0)
        text = "ALERT  " + alerts[0] + (f"  (+{len(alerts)-1})" if len(alerts) > 1 else "")
        d.text((pad+18, 419), fit(text, font(29, True), W-2*pad-36, d), font=font(29, True), fill=255, anchor="lm")

    # --- upcoming events ---
    d.text((pad, 466+dy), "UPCOMING", font=font(34, True), fill=0)
    y = 516 + dy
    if events is None:
        d.text((pad, y), "Calendar not set up", font=font(31), fill=110)
        y += 47
    elif not events:
        d.text((pad, y), "No upcoming events", font=font(31), fill=110)
        y += 47
    else:
        for day, tm, title in events:
            d.text((pad, y), day, font=font(29, True), fill=0)
            d.text((pad+185, y), tm, font=font(29), fill=40)
            d.text((pad+350, y), fit(title, font(31), W-pad-(pad+350), d), font=font(31), fill=0)
            y += 47
    if countdown:
        d.rounded_rectangle((pad, y+8, W-pad, y+58), radius=10, outline=0, width=3)
        d.text((pad+18, y+33), fit("Countdown   " + countdown, font(28, True), W-2*pad-36, d),
               font=font(28, True), fill=0, anchor="lm")
        y += 66
    y_line = max(y + 20, 835 + dy)
    d.line([pad, y_line, W-pad, y_line], fill=0, width=5)

    # --- home (Nest) placeholder ---
    top = y_line + 17
    d.text((pad, top), "HOME", font=font(34, True), fill=0)
    d.text((pad, top+53), "--\u00b0", font=font(118, True), fill=150)
    d.text((pad+245, top+73), "Thermostat", font=font(27), fill=40)
    d.text((pad+245, top+116), "not connected", font=font(26, True), fill=0)
    d.line([520, top+8, 520, top+278], fill=0, width=3)

    # --- cat / litter ---
    lit = ctx.get("litter")
    d.text((560, top), "CAT", font=font(34, True), fill=0)
    draw_cat(d, 655, top+136, 170, lit["mood"] if lit else "ok")
    d.text((775, top+63), "Litter box", font=font(27), fill=40)
    if lit:
        d.text((775, top+100), lit["headline"], font=font(30, True), fill=0)
        d.text((775, top+150), lit["sub"], font=font(26, True if lit["mood"] == "grumpy" else False), fill=0 if lit["mood"] == "grumpy" else 40)
    else:
        d.text((775, top+100), "not tracked", font=font(30, True), fill=0)
        d.text((775, top+150), "yet", font=font(26), fill=40)
    filled = lit["filled"] if lit else 0
    bx, by, bw, bh, gap = 560, top+256, 98, 26, 12
    for i in range(4):
        x = bx + i*(bw+gap)
        if i < filled:
            d.rectangle((x, by, x+bw, by+bh), fill=0)
        else:
            d.rectangle((x, by, x+bw, by+bh), outline=0, width=3, fill=255)

    d.text((W-pad, H-36), f"Updated {now.strftime('%-I:%M %p')}", font=font(26), fill=110, anchor="rs")
    return img


def safe(label, fn, default=None):
    try:
        return fn()
    except Exception as e:
        # Only the error type is printed: messages can contain private links.
        print(f"{label} failed:", type(e).__name__)
        return default


def main():
    now = datetime.now(ZoneInfo(TZ))
    ctx = {
        "now": now,
        "weather": safe("Weather", fetch_weather),
        "aqi": safe("Air quality", fetch_air),
        "alerts": safe("Alerts", lambda: fetch_alerts(now), []),
        "events": safe("Calendar", lambda: get_events(now), (None, None)),
        "litter": safe("Litter", lambda: load_litter(now)),
    }
    render(ctx).save(OUT)
    print("Saved", OUT)


if __name__ == "__main__":
    main()
