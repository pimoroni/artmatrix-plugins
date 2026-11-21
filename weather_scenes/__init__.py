"""Weather Scenes: the weather outside as a little animated landscape.

A warm clear day is a beach, a cooler one the countryside as the season has
it: blossom in spring, full leaf in summer, falling leaves in autumn and a bare
tree in winter. Rain falls from grey cloud, snow settles, fog rolls over the
land, and a tree sways harder the stronger the wind blows. Night, sunrise and
sunset light the whole scene. A few days of the year dress it up, as festive.py
has them: Christmas, Halloween, Bonfire Night and New Year.

This file fetches the weather from Open-Meteo, turns it into the state dict
`w`, and calls the layers in sky.py and scenery.py to draw it, then puts the
temperature in a corner or the middle: on a plain card, or blended in by
temperature.py, with the weather passing behind and in front. With show set to "demo" it steps
through every kind of scene instead, without the network.
"""

import math
import time

from fetch import AsyncFetch
from plugin_config import plugin_config
from qr_screen import draw_qr_screen

# the sky and the land have a file each, loaded by path the way the host loads
# this one. "from plugins.weather_scenes import sky" would run this file again
sky = __import__(__name__ + "/sky")
scenery = __import__(__name__ + "/scenery")
temperature = __import__(__name__ + "/temperature")
festive = __import__(__name__ + "/festive")

# °c a clear or fair day must reach to be a beach day, the choices on the settings page
BEACH_FROM = (18, 20, 22, 25)

# in the order the year has them, from december: three months each
SEASONS = ("winter", "spring", "summer", "autumn")

# where the temperature can go
PLACES = ("top-left", "top-right", "bottom-left", "bottom-right", "centre", "none")
# the days festive.py dresses the scene up for
THEMES = ("christmas", "halloween", "bonfire", "newyear")

# These values are exposed to the web interface
cfg = plugin_config("weather_scenes", {
    "lat": None,  # blank uses the weather plugin's location
    "lng": None,
    "units": "celsius",  # celsius or fahrenheit
    "text": "bottom-left",  # where the temperature goes: one of PLACES
    "blend": "on",  # on has temperature.py stand it in the scene, off puts it on a card
    "beach": 20,  # one of BEACH_FROM
    "season": "auto",  # auto, by the calendar, or one of SEASONS
    "theme": "auto",  # auto, by the calendar, off, or one of THEMES
    "show": "live",  # live, or demo to step through every scene
})
lat = cfg["lat"]
lng = cfg["lng"]
units = cfg["units"] if cfg["units"] in ("celsius", "fahrenheit") else "celsius"
text = cfg["text"] if cfg["text"] in PLACES else "bottom-left"
blend = cfg["blend"] if cfg["blend"] in ("on", "off") else "on"
if cfg["text"] == "corner":
    # the setting before there was a choice of corner: the card in the bottom left
    blend = "off"
blended = blend == "on" and text != "none"
# in a bottom corner the temperature stands in the grass, so it's drawn before it
low = blended and text.startswith("bottom")
if blended:
    temperature.stand(text)
beach = cfg["beach"] if cfg["beach"] in BEACH_FROM else 20
season = cfg["season"] if cfg["season"] in SEASONS else "auto"
theme = cfg["theme"] if cfg["theme"] in THEMES or cfg["theme"] == "off" else "auto"
show = cfg["show"] if cfg["show"] in ("live", "demo") else "live"


def read_location(saved):
    # lat and lng as floats, or None if either is missing or isn't a number
    try:
        return float(saved["lat"]), float(saved["lng"])
    except (TypeError, ValueError):
        return None


# our own setting, or else the weather plugin's, so a board that already shows the
# weather needn't be told where it is twice
location = read_location(cfg) or read_location(plugin_config("weather", {"lat": None, "lng": None}))

API_HOST = "api.open-meteo.com"
UPDATE_INTERVAL = 600   # 10 minutes

# daylight comes up and goes down over TWILIGHT minutes, centred on sunrise and sunset
TWILIGHT = 45
# the warm glow is brightest at sunrise and sunset, and gone GLOW minutes either side
GLOW = 45
# the light moves on every LIGHT_STEP seconds, in steps of 1 / LIGHT_LEVELS, so the
# layers only have to redraw what they keep now and then
LIGHT_STEP = 5
LIGHT_LEVELS = 50

# the moon's phase counts days from a known new moon, 18:14 utc on 6 jan 2000, in lunar months
LUNAR_MONTH = 29.530588853
KNOWN_NEW_MOON = time.mktime((2000, 1, 6, 18, 14, 0, 0, 0))

# the board's clock is utc, set over the network, and reads 2021 until it is. till
# then the time open-meteo sent, moved on by how long ago it came, stands in
CLOCK_SET = time.mktime((2025, 1, 1, 0, 0, 0, 0, 0))

SNOW_CODES = (71, 73, 75, 77, 85, 86)

# every scene worth seeing, DEMO_SECONDS each when show is "demo". each is a reading
# as open-meteo would send it, then the light: the name, weather code, °c, cloud cover %,
# wind and gusts in km/h, where the wind blows from in degrees (270, the west, blows
# left to right), day, dusk, the moon's phase, the season and the theme, unless their
# settings name one. beach days are 25 °c or more, so they're beaches whatever the beach
# setting
DEMO_SECONDS = 10
DEMO = (
    # name                   code  °c  cloud wind gust from day  dusk moon season    theme
    ("beach, calm",             0,  28,   5,   4,   8, 270, 1,   0,   0.5, "summer", None),
    ("beach, windy",            1,  26,  20,  38,  60,  90, 1,   0,   0.5, "summer", None),
    ("beach at sunset",         0,  25,  10,  10,  16, 250, 0.5, 1,   0.5, "summer", None),
    ("spring, sunny",           1,  14,  15,  12,  20, 250, 1,   0,   0.5, "spring", None),
    ("summer, breezy",          1,  18,  15,  15,  28, 250, 1,   0,   0.5, "summer", None),
    ("autumn, partly cloudy",   2,  12,  45,  10,  18, 300, 1,   0,   0.5, "autumn", None),
    ("winter, clear",           0,   6,  10,   8,  14, 280, 1,   0,   0.5, "winter", None),
    ("autumn in a gale",        2,  12,  75,  70, 100, 240, 1,   0,   0.5, "autumn", None),
    ("overcast in winter",      3,   7, 100,  12,  20, 200, 1,   0,   0.5, "winter", None),
    ("spring drizzle",         53,   9, 100,   8,  15, 220, 1,   0,   0.5, "spring", None),
    ("spring showers",         80,  13,  60,  20,  35, 260, 1,   0,   0.5, "spring", None),
    ("heavy rain in autumn",   65,  10, 100,  30,  50, 230, 1,   0,   0.5, "autumn", None),
    ("summer storm with hail", 96,  18, 100,  40,  75, 260, 1,   0,   0.5, "summer", None),
    ("autumn fog",             45,   6, 100,   3,   5,   0, 1,   0,   0.5, "autumn", None),
    ("snow",                   73,  -1, 100,  12,  20,  20, 1,   0,   0.5, "winter", None),
    ("frosty dawn",             0,  -3,   5,   5,   8,  90, 0.5, 1,   0.5, "winter", None),
    ("summer night with moon",  0,  12,   0,   6,  10, 250, 0,   0,   0.4, "summer", None),
    ("snowy night",            71,  -2, 100,   8,  14,  10, 0,   0,   0.5, "winter", None),
    ("halloween",               1,  11,  20,  10,  18, 250, 1,   0,   0.5, "autumn", "halloween"),
    ("halloween night",         0,   9,  10,  10,  18, 250, 0,   0,   0.5, "autumn", "halloween"),
    ("bonfire night",           1,   7,  20,   8,  14, 250, 0,   0,   0.3, "autumn", "bonfire"),
    ("christmas day",           1,   5,  20,   8,  14, 270, 1,   0,   0.5, "winter", "christmas"),
    ("christmas eve, snowing", 71,  -2, 100,   6,  10,  10, 0,   0,   0.5, "winter", "christmas"),
    ("new year's eve",          0,   4,   0,   5,   9, 260, 0,   0,   0.6, "winter", "newyear"),
)


# the state the layers draw from. it's filled in here and only read there, and it's
# the same dict every frame
w = {
    "land": "summer",  # beach, frost, snow, or the countryside in one of SEASONS
    "theme": None,     # one of THEMES on its days, for festive.py
    "year": 0,         # the year to write in the sky at new year
    "sky": "clear",    # clear, partly, cloudy, overcast, fog, drizzle, rain, showers, snow or storm
    "code": 0,         # the wmo weather code
    "temp": 15.0,      # °c
    "cloud": 0,        # cover, 0 to 100 %
    "wind": 0.0,       # km/h
    "gust": 0.0,       # km/h, never less than wind
    "push": 0.0,       # km/h, the full wind speed, + blowing left to right
    "day": 1.0,        # 1 day, 0 night
    "dusk": 0.0,       # 1 at sunrise and sunset
    "moon": 0.5,       # phase: 0 new, 0.5 full
    "rain": 0,         # 0 none to 3 heavy
    "snow": 0,         # 0 none to 3 heavy
    "hail": False,
    "storm": False,
    "fog": 0.0,        # 0 clear to 1 thick
    # goes up by one whenever anything above changes. it starts somewhere new each
    # import: sky and scenery stay imported when the settings reload this file, and
    # their caches mustn't look current
    "change": time.ticks_ms() & 0xFFFF,
    # where the land meets the sky, from scenery, so the sky needn't import it
    "horizon": scenery.HORIZON,
    # the moon's lit side swaps south of the equator
    "south": location is not None and location[0] < 0,
}


def choose_scene(code, temp, cloud, time_of_year):
    # what to draw for a wmo weather code (https://open-meteo.com/en/docs), the
    # temperature in °c, the cloud cover in % and the season. rain and snow run from
    # 0, none, to 3, heavy. fog from 0 to 1
    rain = snow = 0
    fog = 0
    if code in (45, 48):            # fog, 48 leaving rime
        kind = "fog"
        fog = 1
    elif 51 <= code <= 57:          # drizzle: light, moderate, dense. 56 and 57 freezing
        kind = "drizzle"
        rain = 1
        fog = 0.2                   # drizzle comes with mist
    elif 61 <= code <= 67:          # rain: 61 slight, 63 moderate, 65 heavy. 66 and 67 freezing
        kind = "rain"
        rain = 3 if code in (65, 67) else 2 if code == 63 else 1
    elif code in SNOW_CODES:        # snow: 71 slight, 73 moderate, 75 heavy, 77 grains. 85 and 86 showers
        kind = "snow"
        snow = 3 if code in (75, 86) else 2 if code == 73 else 1
    elif 80 <= code <= 82:          # rain showers: slight, moderate, violent
        kind = "showers"
        rain = code - 79
    elif code >= 95:                # thunderstorm, with hail for 96 and 99
        kind = "storm"
        rain = 3 if code == 99 else 2
    elif code == 3:
        kind = "overcast"
    elif code == 2:                 # partly cloudy, or more when the cover says so
        kind = "cloudy" if cloud >= 60 else "partly"
    elif code == 1:                 # mainly clear
        kind = "partly"
    elif code == 0:
        kind = "clear"
    else:                           # a code open-meteo doesn't send
        kind = "cloudy"
    if rain == 3 or snow == 3:
        fog = 0.3                   # heavy rain and snow hide the distance

    if code in SNOW_CODES:
        land = "snow"
    elif code <= 2 and temp >= beach:
        land = "beach"
    elif temp < 3:
        land = "frost"
    else:
        land = time_of_year

    return {"land": land, "sky": kind, "rain": rain, "snow": snow, "fog": fog,
            "hail": code in (96, 99), "storm": code >= 95}


def reading(code, temp, cloud, wind, gust, direction, time_of_year):
    # w's values for a reading: the scene for it, and the reading itself
    values = choose_scene(code, temp, cloud, time_of_year)
    values["code"] = code
    values["temp"] = temp
    values["cloud"] = cloud
    values["wind"] = wind
    values["gust"] = max(gust, wind)
    # the direction is where the wind comes from, so a westerly blows left to right.
    # the push keeps the full speed, so wind blowing straight at us still sways things
    values["push"] = wind if -math.sin(math.radians(direction)) >= 0 else -wind
    return values


def settle(values):
    # copy values into w, counting one change if any of them is new
    changed = False
    for key in values:
        if w[key] != values[key]:
            w[key] = values[key]
            changed = True
    if changed:
        w["change"] += 1


# from the last reply: open-meteo's reading, the local minutes past midnight of
# sunrise and sunset, the seconds local time is ahead of utc, and the time it was sent
# (utc) with ticks_ms when it came
weather = None
sunrise = None
sunset = None
utc_offset = 0
is_day = True
reply_time = None
reply_ticks = 0


def utc_now():
    now = time.time()
    if now < CLOCK_SET and reply_time is not None:
        now = reply_time + time.ticks_diff(time.ticks_ms(), reply_ticks) // 1000
    return now


def light(now):
    # day, dusk and the moon at now, in seconds since the epoch, utc
    minute = (now + utc_offset) // 60 % 1440
    if sunrise < sunset:
        up = (minute - sunrise) / TWILIGHT + 0.5
        down = (sunset - minute) / TWILIGHT + 0.5
        day = max(0, min(up, down, 1))
        nearest = min(abs(minute - sunrise), abs(minute - sunset))
        dusk = max(0, 1 - nearest / GLOW)
    else:
        # near the poles the sun can stay up or down all day
        day = 1 if is_day else 0
        dusk = 0
    phase = (now - KNOWN_NEW_MOON) / 86400 % LUNAR_MONTH / LUNAR_MONTH
    return {"day": round(day * LIGHT_LEVELS) / LIGHT_LEVELS,
            "dusk": round(dusk * LIGHT_LEVELS) / LIGHT_LEVELS,
            "moon": round(phase * 100) / 100 % 1}


def season_now():
    # the season setting, or the one the calendar gives where we are: three months
    # each from december, and half a year on south of the equator
    if season != "auto":
        return season
    month = time.gmtime(utc_now() + utc_offset)[1]
    return SEASONS[(month % 12 // 3 + (2 if w["south"] else 0)) % 4]


def dressing(named="auto"):
    # w's theme and year: the theme named, or the theme setting, or else the one the
    # calendar gives. christmas runs from 1 december to twelfth night, with new year's
    # eve and day taken out of it for new year. halloween has the week up to it
    year, month, day = time.gmtime(utc_now() + utc_offset)[0:3]
    if theme != "auto":
        named = theme
    if named == "auto":
        if (month, day) in ((12, 31), (1, 1)):
            named = "newyear"
        elif month == 12 or (month == 1 and day <= 5):
            named = "christmas"
        elif month == 10 and day >= 25:
            named = "halloween"
        elif (month, day) == (11, 5):
            named = "bonfire"
    # in the second half of the year it's the one about to start
    return {"theme": named if named in THEMES else None, "year": year + 1 if month > 6 else year}


def minutes(stamp):
    # local minutes past midnight, from a time like "2026-10-28T07:12"
    return int(stamp[11:13]) * 60 + int(stamp[14:16])


if location is not None and show == "live":
    API_PATH = f"/v1/forecast?latitude={location[0]}&longitude={location[1]}&current=temperature_2m,is_day,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m&daily=sunrise,sunset&forecast_days=1&timezone=auto"
    api_data = AsyncFetch(API_HOST)
    api_data.fetch(API_PATH, interval=UPDATE_INTERVAL)

    @api_data.on_complete
    def complete(fetch):
        global weather, sunrise, sunset, utc_offset, is_day, reply_time, reply_ticks
        try:
            data = fetch.to_json()
            current = data["current"]
            # local times like "2026-10-28T07:12"
            sunrise = minutes(data["daily"]["sunrise"][0])
            sunset = minutes(data["daily"]["sunset"][0])
            utc_offset = data["utc_offset_seconds"]
            is_day = current["is_day"] == 1
            stamp = current["time"]
            reply_time = time.mktime((int(stamp[0:4]), int(stamp[5:7]), int(stamp[8:10]),
                                      int(stamp[11:13]), int(stamp[14:16]), 0, 0, 0)) - utc_offset
            reply_ticks = time.ticks_ms()
            # celsius and km/h. cloud and gusts can come back empty
            wind = current["wind_speed_10m"]
            weather = reading(current["weather_code"], current["temperature_2m"], current["cloud_cover"] or 0,
                              wind, current["wind_gusts_10m"] or wind, current["wind_direction_10m"], season_now())
        except (KeyError, IndexError, TypeError, ValueError) as e:
            # keep the last good reading, and try again at the next interval
            print("weather scenes: couldn't read the reply:", repr(e))
            return
        weather.update(light(utc_now()))
        weather.update(dressing())
        settle(weather)

    @api_data.on_error
    def error(fetch):
        # not the body: an error can quote the location back. the next fetch is at the
        # usual interval
        print("weather scenes: HTTP", fetch.http_status)
        return True


# where the demo is, and the t to move on at
demo_at = 0
demo_next = 0


def play_demo(index):
    # show DEMO[index] now, and move on DEMO_SECONDS later
    global demo_at, demo_next
    demo_at = index
    demo_next = clock_ms / 1000 + DEMO_SECONDS
    _name, code, temp, cloud, wind, gust, direction, day, dusk, moon, time_of_year, named = DEMO[index]
    values = reading(code, temp, cloud, wind, gust, direction, time_of_year if season == "auto" else season)
    values.update(dressing(named))
    values["day"] = day
    values["dusk"] = dusk
    values["moon"] = moon
    settle(values)


# t, the seconds since import the layers are given, kept in whole ms so it never wraps.
# the light moves on at light_at
clock_ms = 0
last_ticks = time.ticks_ms()
light_at = 0

if show == "demo":
    play_demo(0)

# the temperature when it isn't blended in: on a dark card, as the weather plugin's corner text
CARD_FONT = font.smart
CARD_MARGIN = 4
CARD_PADDING = 3
CARD_RADIUS = 3
# a little darker than the weather plugin's, for white text over snow and sand
CARD_PEN = color.rgb(0, 0, 0, 150)
WHITE = color.rgb(255, 255, 255)
# rebuilt only when the temperature changes. card_temp is the °c it was built for
card_temp = None
card_label = None
card = None
card_at = None

LOADING_SKY = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(30, 72, 124)), (1.0, color.rgb(88, 128, 168))))

# seconds a new scene takes to fade in over the last frame of the old one
FADE_TIME = 1.5
# a gap this long between frames means the plugin was off screen, and the surface
# may not hold its last frame any more
FADE_GAP_MS = 1000
previous = image(screen.width, screen.height)
fade_left = 0
# the land and sky on screen, "loading" before the first reading, None before the
# first frame. and the surface they're on
shown_land = None
shown_sky = None
last_screen = None


def draw_card():
    global card_temp, card_label, card, card_at
    screen.font = CARD_FONT
    if w["temp"] != card_temp:
        card_temp = w["temp"]
        degrees = card_temp * 9 / 5 + 32 if units == "fahrenheit" else card_temp
        card_label = f"{round(degrees)}°"
        width, height = screen.measure_text(card_label, 1)
        # always square, sized by the longer side of the text
        size = max(width, height) + CARD_PADDING * 2
        x = (CARD_MARGIN if text.endswith("left") else screen.width - CARD_MARGIN - size if text.endswith("right")
             else (screen.width - size) // 2)
        y = (CARD_MARGIN if text.startswith("top") else screen.height - CARD_MARGIN - size if text.startswith("bottom")
             else (screen.height - size) // 2)
        card = shape.rounded_rectangle(x, y, size, size, CARD_RADIUS)
        # whole pixels, or the pixel font blurs
        card_at = vec2(round(x + (size - width) / 2), round(y + (size - height) / 2))
    screen.pen = CARD_PEN
    screen.shape(card)
    screen.pen = WHITE
    screen.text(card_label, card_at, 1)


def draw_loading():
    screen.pen = LOADING_SKY
    screen.clear()
    screen.font = CARD_FONT
    width, height = screen.measure_text("Loading", 1)
    screen.pen = WHITE
    screen.text("Loading", vec2(round((screen.width - width) / 2), round((screen.height - height) / 2)), 1)


def update():
    global clock_ms, last_ticks, light_at, fade_left, shown_land, shown_sky, last_screen

    ticks = time.ticks_ms()
    step = time.ticks_diff(ticks, last_ticks)
    last_ticks = ticks
    clock_ms += step
    t = clock_ms / 1000

    if show == "demo":
        if t >= demo_next:
            play_demo((demo_at + 1) % len(DEMO))
    elif location is None:
        draw_qr_screen("Weather Scenes", "Setup needed", "weather_scenes")
        return
    else:
        try:
            api_data.update()
        except (OSError, ValueError) as e:
            # no connection, or it dropped. the fetch is tried again in 30 seconds,
            # and the scene carries on with the last reading
            print("weather scenes: fetch failed:", repr(e))
        if weather is not None and t >= light_at:
            light_at = t + LIGHT_STEP
            settle(light(utc_now()))

    ready = show == "demo" or weather is not None
    if ready:
        land = w["land"]
        kind = w["sky"]
    else:
        land = kind = "loading"

    # the screen still holds the last frame. keep it to fade out over a new scene, but
    # not on the first frame, or one on a surface that may hold something else
    if land != shown_land or kind != shown_sky:
        if shown_land is not None and screen is last_screen and step < FADE_GAP_MS:
            memoryview(previous)[:] = memoryview(screen)
            fade_left = FADE_TIME
        shown_land = land
        shown_sky = kind
    last_screen = screen

    screen.antialias = image.X4
    if ready:
        sky.background(w, t)
        sky.lights(w, t)
        sky.clouds(w, t)
        if w["theme"]:
            festive.behind(w, t)
        scenery.land(w, t)
        scenery.tree(w, t)
        if w["theme"]:
            festive.front(w, t)
        if low:
            temperature.draw(w, units)
        scenery.foreground(w, t)
        sky.fog(w, t)
        if blended:
            # the far rain and snow fall behind the temperature, the near in front
            sky.precipitation(w, t, False)
            if not low:
                temperature.draw(w, units)
            sky.precipitation(w, t, True, temperature.LAYER, temperature.top)
        else:
            sky.precipitation(w, t)
        sky.lightning(w, t)
        if text != "none" and not blended:
            draw_card()
    else:
        draw_loading()

    if fade_left > 0:
        # at most a quarter second a frame, so a slow one doesn't cut the fade short
        fade_left -= min(step, 250) / 1000
        screen.alpha = int(255 * max(fade_left, 0) / FADE_TIME)
        screen.blit(previous, 0, 0)
        screen.alpha = 255
