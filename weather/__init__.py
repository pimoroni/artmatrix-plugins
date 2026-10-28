import time
from fetch import AsyncFetch, HTTPException
import math
from random import randint, uniform

from plugin_config import plugin_config
from qr_screen import draw_qr_screen

CY = screen.height / 2

cfg = plugin_config("weather", {
    "lat": None,
    "lng": None,
    "units": "celsius",  # celsius or fahrenheit
})
lat = cfg["lat"]
long = cfg["lng"]
units = cfg["units"]
if units not in ("celsius", "fahrenheit"):
    units = "celsius"
if lat is not None:
    lat = float(lat)
if long is not None:
    long = float(long)


has_location = True
if None in (lat, long):
    has_location = False

API_HOST = "api.open-meteo.com"
API_PATH = f"/v1/forecast?latitude={lat}&longitude={long}&current_weather=true&daily=sunrise,sunset&forecast_days=1&timezone=auto"
UPDATE_INTERVAL = 600   # 10 minutes

weathercode = None
temperature = None
is_day = None
# minutes past local midnight, and seconds the local time is ahead of utc
sunrise_minute = None
sunset_minute = None
utc_offset = None
# from the wind. cloud and snow drift in px a second, rain in px sideways per px of fall
cloud_drift = None
snow_drift = None
rain_slant = None

# rain, snow and storms have cloud above CLOUD_BASE. their background is clear down
# to CLOUD_FADE_START of the screen, then fades in to solid at CLOUD_BASE
CLOUD_BASE = 58
CLOUD_FADE_START = 0.15
CLOUD_FADE_END = CLOUD_BASE / screen.height

snowy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(109, 129, 150, 0)), (CLOUD_FADE_START, color.rgb(109, 129, 150, 0)), (CLOUD_FADE_END, color.rgb(109, 129, 150)), (1.0, color.rgb(150, 165, 185))))
rainy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(105, 105, 105, 0)), (CLOUD_FADE_START, color.rgb(105, 105, 105, 0)), (CLOUD_FADE_END, color.rgb(105, 105, 105)), (1.0, color.rgb(80, 123, 156))))
stormy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(105, 105, 105, 0)), (CLOUD_FADE_START, color.rgb(105, 105, 105, 0)), (CLOUD_FADE_END, color.rgb(105, 105, 105)), (1.0, color.rgb(70, 70, 70))))
sky_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(58, 124, 190)), (1.0, color.rgb(160, 200, 232))))

over_cloud = brush.fractal(screen.height * 0.45, 4, 0.72, 0, 7719)
over_cloud.ramp((
    (0.00, color.rgb(28, 32, 38)),
    (0.35, color.rgb(58, 64, 72)),
    (0.62, color.rgb(96, 104, 114)),
    (0.84, color.rgb(150, 158, 168)),
    (0.92, color.rgb(198, 204, 212)),
    (1.00, color.rgb(238, 240, 244)),
))


light_cloud = brush.fractal(screen.height * 0.45, 4, 0.72, 0, 7719)
light_cloud.ramp((
    (0.00, color.rgb(255, 255, 255, 0)),
    (0.45, color.rgb(255, 255, 255, 0)),
    (0.60, color.rgb(240, 244, 248, 80)),
    (0.75, color.rgb(245, 247, 250, 255)),
    (0.88, color.rgb(200, 205, 212, 255)),
    (1.00, color.rgb(160, 166, 175, 255)),
))

# same seed as over_cloud, darker, for the band over rain, snow and storms
heavy_cloud = brush.fractal(screen.height * 0.45, 4, 0.72, 0, 7719)
heavy_cloud.ramp((
    (0.00, color.rgb(34, 38, 46)),
    (0.40, color.rgb(56, 62, 72)),
    (0.70, color.rgb(90, 96, 106)),
    (1.00, color.rgb(130, 136, 146)),
))

sun_grad = brush.gradient(brush.RADIAL, 15, 15, 0, 0, ((0.0, color.rgb(255, 210, 120)), (1.0, color.rgb(255, 180, 40))))

SUN_CENTRE = vec2(15, 15)
SUN_RADIUS = 15
SUN_RAYS = 50
# long enough to reach the far corner from the sun
RAY_LENGTH = 170
# degrees a second
RAY_TURN = 5

# rays alternate bright and dim. each set is one shape, built once and turned by its transform
bright_paths = []
dim_paths = []
for i in range(SUN_RAYS):
    start = math.radians(360 / SUN_RAYS * i)
    end = math.radians(360 / SUN_RAYS * (i + 1))
    ray = [vec2(0, 0),
           vec2(math.cos(start) * RAY_LENGTH, math.sin(start) * RAY_LENGTH),
           vec2(math.cos(end) * RAY_LENGTH, math.sin(end) * RAY_LENGTH)]
    if i % 2:
        bright_paths.append(ray)
    else:
        dim_paths.append(ray)
bright_rays = shape.custom(*bright_paths)
dim_rays = shape.custom(*dim_paths)

night_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(6, 10, 30)), (1.0, color.rgb(28, 40, 78))))

# laid over the cloudy, wet and foggy scenes after dark
night_overlay = color.rgb(6, 10, 30, 150)
# lighter for fog, which vanishes under the full one
fog_night_overlay = color.rgb(6, 10, 30, 80)

# same seed as light_cloud, so the clouds keep their shape after dark
night_cloud = brush.fractal(screen.height * 0.45, 4, 0.72, 0, 7719)
night_cloud.ramp((
    (0.00, color.rgb(40, 46, 66, 0)),
    (0.45, color.rgb(40, 46, 66, 0)),
    (0.60, color.rgb(70, 76, 98, 80)),
    (0.75, color.rgb(78, 84, 106, 255)),
    (0.88, color.rgb(58, 64, 84, 255)),
    (1.00, color.rgb(44, 50, 70, 255)),
))

MOON_X = 20
MOON_Y = 20
MOON_RADIUS = 9
MOON_HALO_RADIUS = 24
moon_halo = brush.gradient(brush.RADIAL, MOON_X, MOON_Y, MOON_X, MOON_Y + MOON_HALO_RADIUS,
                           ((0.0, color.rgb(150, 160, 200, 120)), (1.0, color.rgb(150, 160, 200, 0))))
# 4 px blobs, 3 octaves, persistence 0.5, no tiling
moon_craters = brush.fractal(4, 3, 0.5, 0, 311)
moon_craters.ramp(((0.0, color.rgb(150, 150, 140)), (0.55, color.rgb(225, 223, 210)), (1.0, color.rgb(225, 223, 210))))

# the phase counts days from a known new moon, 18:14 utc on 6 jan 2000, in lunar months
LUNAR_MONTH = 29.530588853
KNOWN_NEW_MOON = time.mktime((2000, 1, 6, 18, 14, 0, 0, 0))
# points along each edge of the moon's shadow, its rim and the line between light and dark
MOON_SHADOW_STEPS = 16
# a little earthshine shows through
MOON_SHADOW_PEN = color.rgb(18, 24, 48, 230)
# the shadow's rim reaches this far past the moon's, so no bright edge shows round it
MOON_SHADOW_OVERLAP = 0.6
# set with each fetch. the shadow's shape, and how much of the moon is lit from 0 to 1
moon_shadow = None
moon_lit = 1

fog_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(120, 128, 136)), (1.0, color.rgb(170, 176, 182))))
fog = brush.fractal(screen.height * 0.3, 3, 0.5, 0, 5113)
fog.ramp((
    (0.00, color.rgb(230, 234, 238, 0)),
    (0.40, color.rgb(230, 234, 238, 0)),
    (0.70, color.rgb(230, 234, 238, 150)),
    (1.00, color.rgb(240, 242, 245, 210)),
))
# the fog's noise is stretched this much sideways, so it lies in banks
FOG_STRETCH = 4

# x, y and twinkle phase
stars = []
for _ in range(40):
    stars.append((randint(0, screen.width - 1), randint(0, screen.height - 30), uniform(0, 6.28)))


# rain levels: drops drawn, drop length in px, fall speed in px a second
DRIZZLE = (40, 2, 30)
RAIN = (100, 4, 50)
HEAVY_RAIN = (160, 6, 70)
RAIN_LEVELS = {
    51: DRIZZLE, 53: DRIZZLE, 55: DRIZZLE, 56: DRIZZLE, 57: DRIZZLE,
    61: RAIN, 63: RAIN, 66: RAIN, 80: RAIN, 81: RAIN,
    65: HEAVY_RAIN, 67: HEAVY_RAIN, 82: HEAVY_RAIN,
}

# speed and length scale, then pen
RAIN_LAYERS = (
    (0.6, color.rgb(255, 255, 255, 40)),   # far
    (0.8, color.rgb(255, 255, 255, 70)),   # middle
    (1.0, color.rgb(255, 255, 255, 110)),  # near
)

# x, y and layer
rain_particles = []
for _ in range(HEAVY_RAIN[0]):
    rain_particles.append([randint(0, screen.width - 1), uniform(0, screen.height), randint(0, 2)])

# snow levels: flakes drawn, and whether a third of them are big near ones.
# then the deepest it settles along the bottom, in px
LIGHT_SNOW = (60, True, 4)
SNOW = (100, True, 8)
HEAVY_SNOW = (150, True, 14)
SNOW_GRAINS = (100, False, 4)
SNOW_LEVELS = {71: LIGHT_SNOW, 73: SNOW, 75: HEAVY_SNOW, 77: SNOW_GRAINS, 85: LIGHT_SNOW, 86: HEAVY_SNOW}

# radius in px, fall speed range in px a second, pen
SNOW_LAYERS = (
    (1, (5, 12), color.rgb(255, 255, 255, 150)),     # far
    (1.6, (14, 20), color.rgb(255, 255, 255, 220)),  # near
)
# px each side flakes sway as they fall
SNOW_SWAY = 6

# x, y, layer, fall speed and sway phase. every third flake is a near one
snow_particles = []
for i in range(HEAVY_SNOW[0]):
    layer = 1 if i % 3 == 0 else 0
    snow_particles.append([randint(0, screen.width - 1), uniform(0, screen.height), layer,
                           uniform(*SNOW_LAYERS[layer][1]), uniform(0, 6.28)])

# settled snow is kept as a depth in px for each SETTLE_WIDTH px column along the bottom.
# a flake that lands adds its level's deepest * SETTLE_RATE / flakes to its column, which
# fills any level in about two minutes. every SETTLE_STEP seconds each column moves
# SETTLE_SMOOTHING of the way to its neighbours' average, so it lies in drifts.
# the drifts' outline is rebuilt as one shape then
SETTLE_WIDTH = 2
SETTLE_COLUMNS = screen.width // SETTLE_WIDTH
SETTLE_RATE = 6
SETTLE_STEP = 0.25
SETTLE_SMOOTHING = 0.5
SETTLED_PEN = color.rgb(235, 240, 248)
# a darker copy of the drifts sits SETTLED_EDGE px higher, so their top edge shows
SETTLED_EDGE_PEN = color.rgb(110, 125, 150)
SETTLED_EDGE = 1.5
snow_depth = [0] * SETTLE_COLUMNS
# seconds to the next rebuild. 0 builds drifts on the first frame
settle_in = 0
drifts = None

# how the wind moves things, per km/h blowing across the panel, and the most it can.
# cloud and snow in px a second, rain in px sideways per px of fall. 0.58 is 30 degrees
CLOUD_DRIFT_PER_KMH = 0.5
MAX_CLOUD_DRIFT = 25
SNOW_DRIFT_PER_KMH = 0.6
MAX_SNOW_DRIFT = 20
RAIN_SLANT_PER_KMH = 0.02
MAX_RAIN_SLANT = 0.58

STORM_CODES = (95, 96, 99)
# seconds between strikes
STRIKE_GAP = (3, 8)
# each strike is a flash then a weaker flicker: start and length in seconds, strength
FLASHES = (
    (0.0, 0.12, 1.0),  # flash
    (0.2, 0.1, 0.6),   # flicker
)
# the bolt starts this far down and zigzags this many steps, staying in the cloud.
# it keeps BOLT_MARGIN px from the sides, and each step moves up to BOLT_JITTER px
# across and BOLT_STEP_DOWN px down
BOLT_TOP = 14
BOLT_STEPS = 6
BOLT_MARGIN = 20
BOLT_JITTER = 6
BOLT_STEP_DOWN = (5, 9)
flash_glow = brush.gradient(brush.LINEAR, 0, 0, 0, CLOUD_BASE, ((0.0, color.rgb(220, 226, 255, 150)), (1.0, color.rgb(220, 226, 255, 0))))
strike_in = 0      # seconds to the next strike
# seconds since the last one, long enough that nothing shows at the start
since_strike = 10
bolt = []

# label under the temperature. 120 px is the widest that fits, and the font won't shrink
LABELS = {
    0: "Sunny", 1: "Fair", 2: "Cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Icy drizzle", 57: "Icy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Icy rain", 67: "Icy rain",
    71: "Light snow", 73: "Snow", 75: "Deep snow", 77: "Fine snow",
    80: "Showers", 81: "Showers", 82: "Downpour", 85: "Flurries", 86: "Deep snow",
    95: "Stormy", 96: "Hail", 99: "Heavy hail",
}

# hail storms: pellets drawn
HAIL_LEVELS = {96: 25, 99: 50}
# pellets bounce once off HAIL_FLOOR, keeping HAIL_BOUNCE of their speed
HAIL_FLOOR = screen.height - 2
HAIL_GRAVITY = 300       # px a second, each second
HAIL_SPEED = (60, 100)   # px a second as they leave the cloud
HAIL_BOUNCE = 0.35
HAIL_RADIUS = 1.2
HAIL_PEN = color.rgb(235, 240, 255, 220)
# x, y, fall speed (negative going up) and whether it has bounced
hail_particles = []
for _ in range(HAIL_LEVELS[99]):
    hail_particles.append([randint(0, screen.width - 1), uniform(0, screen.height), uniform(*HAIL_SPEED), False])

# warm light from the bottom, strongest at sunrise and sunset, gone GLOW_MINUTES either side
GLOW_MINUTES = 45
dusk_glow = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(255, 110, 90, 0)), (0.45, color.rgb(255, 110, 90, 50)), (1.0, color.rgb(255, 150, 60, 170))))

# seconds a new scene takes to fade in over the last frame of the old one
FADE_TIME = 1.5
previous = image(screen.width, screen.height)
fade_left = 0
shown_scene = (weathercode, is_day)


def draw_rainy(elapsed, level):
    drops, length, speed = level
    for i in range(drops):
        drop = rain_particles[i]
        scale, pen = RAIN_LAYERS[drop[2]]
        fall = speed * scale * elapsed
        drop[1] += fall
        drop[0] = (drop[0] + fall * rain_slant) % screen.width
        if drop[1] > screen.height:
            drop[1] = 0
            drop[0] = randint(0, screen.width - 1)

        tail = length * scale
        screen.pen = pen
        screen.line(drop[0], drop[1], drop[0] - tail * rain_slant, drop[1] - tail)


def draw_snow(now, elapsed, level):
    global settle_in, drifts
    flakes, big_flakes, deepest = level
    per_flake = deepest * SETTLE_RATE / flakes
    for i in range(flakes):
        flake = snow_particles[i]
        layer = flake[2] if big_flakes else 0
        radius, _, pen = SNOW_LAYERS[layer]
        flake[1] += flake[3] * elapsed
        flake[0] = (flake[0] + snow_drift * elapsed) % screen.width
        x = flake[0] + math.sin(now + flake[4]) * SNOW_SWAY
        # only flakes low enough to reach the snow need their column checked
        if flake[1] > screen.height - deepest:
            column = int(x) // SETTLE_WIDTH % SETTLE_COLUMNS
            if flake[1] > screen.height - snow_depth[column]:
                if snow_depth[column] < deepest:
                    snow_depth[column] += per_flake
                flake[1] = 0
                flake[0] = randint(0, screen.width - 1)

        screen.pen = pen
        screen.circle(x, flake[1], radius)

    settle_in -= elapsed
    if settle_in <= 0:
        settle_in = SETTLE_STEP
        for i in range(SETTLE_COLUMNS):
            # the neighbours wrap round the edges
            around = (snow_depth[i - 1] + snow_depth[(i + 1) % SETTLE_COLUMNS]) / 2
            snow_depth[i] += (around - snow_depth[i]) * SETTLE_SMOOTHING

        outline = [vec2(0, screen.height)]
        for i in range(SETTLE_COLUMNS):
            outline.append(vec2(i * SETTLE_WIDTH + SETTLE_WIDTH / 2, screen.height - snow_depth[i]))
        outline.append(vec2(screen.width, screen.height))
        drifts = shape.custom(outline)

    drifts.transform = mat3().translate(0, -SETTLED_EDGE)
    screen.pen = SETTLED_EDGE_PEN
    screen.shape(drifts)
    drifts.transform = mat3()
    screen.pen = SETTLED_PEN
    screen.shape(drifts)


def draw_sunny(now):
    turn = mat3.trs(SUN_CENTRE, now * RAY_TURN)
    bright_rays.transform = turn
    dim_rays.transform = turn

    screen.pen = color.white
    screen.alpha = 90
    screen.shape(bright_rays)
    screen.alpha = 40
    screen.shape(dim_rays)

    screen.alpha = 255
    screen.pen = sun_grad
    screen.circle(SUN_CENTRE.x, SUN_CENTRE.y, SUN_RADIUS)


def draw_moon(now):
    for x, y, phase in stars:
        brightness = 110 + int(math.sin(now * 1.5 + phase) * 80)
        screen.pen = color.rgb(255, 255, 255, brightness)
        screen.rectangle(x, y, 1, 1)

    screen.alpha = int(255 * moon_lit)
    screen.pen = moon_halo
    screen.circle(MOON_X, MOON_Y, MOON_HALO_RADIUS)
    screen.alpha = 255
    screen.pen = moon_craters
    screen.circle(MOON_X, MOON_Y, MOON_RADIUS)
    screen.pen = MOON_SHADOW_PEN
    screen.shape(moon_shadow)


cloud_at = vec2(0.0, 0.0)
last = 0


def draw_cloud_band():
    heavy_cloud.transform = mat3().translate(cloud_at)
    screen.pen = heavy_cloud
    screen.rectangle(0, 0, screen.width, CLOUD_BASE)


def draw_overcast():
    over_cloud.transform = mat3().translate(cloud_at)
    screen.pen = over_cloud
    screen.clear()


def draw_light_cloud():
    cloud = light_cloud if is_day else night_cloud
    cloud.transform = mat3().translate(cloud_at)
    screen.pen = cloud
    screen.clear()


TEXT_SHADOW = color.rgb(0, 0, 0, 100)
# pale snow needs a darker shadow for the white text to stand out
SNOW_TEXT_SHADOW = color.rgb(20, 30, 50, 220)


def centre_text(text, cy=None, max_size=12, min_size=1, padding=4, colour=color.white, shadow=TEXT_SHADOW):

    max_width = screen.width - padding * 2
    size = max_size
    while size > min_size:
        tw, th = screen.measure_text(text, size)
        if tw <= max_width:
            break
        size -= 1
    tw, th = screen.measure_text(text, size)
    cx = screen.width / 2
    if cy is None:
        cy = screen.height / 2

    screen.pen = shadow
    screen.text(text, vec2((cx - tw / 2) + 2, (cy - th / 2) + 2), size)

    screen.pen = colour
    screen.text(text, vec2(cx - tw / 2, cy - th / 2), size)


if has_location:
    api_data = AsyncFetch(API_HOST, debug=True)
    api_data.fetch(API_PATH, interval=UPDATE_INTERVAL)

    @api_data.on_complete
    def complete(fetch):
        global weathercode, temperature, is_day, cloud_drift, snow_drift, rain_slant
        global sunrise_minute, sunset_minute, utc_offset, moon_shadow, moon_lit

        data = fetch.to_json()

        # 0 at new moon, 0.5 at full
        phase = (time.time() - KNOWN_NEW_MOON) / 86400 % LUNAR_MONTH / LUNAR_MONTH
        # where light meets dark across the moon. 1 at its dark edge, -1 at its lit one
        squash = math.cos(phase * 2 * math.pi)
        moon_lit = (1 - squash) / 2
        # dark on the left while it waxes. the other way round south of the equator
        side = -1 if (phase < 0.5) == (lat >= 0) else 1
        outline = []
        rim = MOON_RADIUS + MOON_SHADOW_OVERLAP
        for i in range(MOON_SHADOW_STEPS + 1):
            angle = math.pi * i / MOON_SHADOW_STEPS
            outline.append(vec2(MOON_X + side * rim * math.sin(angle), MOON_Y - rim * math.cos(angle)))
        for i in range(MOON_SHADOW_STEPS, -1, -1):
            angle = math.pi * i / MOON_SHADOW_STEPS
            outline.append(vec2(MOON_X - side * squash * MOON_RADIUS * math.sin(angle), MOON_Y - MOON_RADIUS * math.cos(angle)))
        moon_shadow = shape.custom(outline)

        # local times like "2026-10-28T07:12"
        sunrise = data["daily"]["sunrise"][0]
        sunset = data["daily"]["sunset"][0]
        sunrise_minute = int(sunrise[11:13]) * 60 + int(sunrise[14:16])
        sunset_minute = int(sunset[11:13]) * 60 + int(sunset[14:16])
        utc_offset = data["utc_offset_seconds"]

        current = data["current_weather"]
        # open-meteo sends celsius
        celsius = current["temperature"]
        if units == "fahrenheit":
            temperature = round(celsius * 9 / 5 + 32)
        else:
            temperature = round(celsius)
        weathercode = current["weathercode"]
        is_day = current["is_day"] == 1

        # km/h blowing left to right. winddirection is where it comes from
        wind_across = -math.sin(math.radians(current["winddirection"])) * current["windspeed"]
        cloud_drift = max(-MAX_CLOUD_DRIFT, min(MAX_CLOUD_DRIFT, wind_across * CLOUD_DRIFT_PER_KMH))
        snow_drift = max(-MAX_SNOW_DRIFT, min(MAX_SNOW_DRIFT, wind_across * SNOW_DRIFT_PER_KMH))
        rain_slant = max(-MAX_RAIN_SLANT, min(MAX_RAIN_SLANT, wind_across * RAIN_SLANT_PER_KMH))

    @api_data.on_error
    def error(fetch):
        print("HTTP", fetch.http_status, fetch.stream.read())
        api_data.fetch(API_PATH, interval=UPDATE_INTERVAL)


def update():
    global cloud_at, last, strike_in, since_strike, bolt, shown_scene, fade_left, settle_in

    if has_location:
        try:
            api_data.update()
        except HTTPException:
            pass

    # the screen still holds the last frame. keep it to fade out over a new scene
    scene = (weathercode, is_day)
    if scene != shown_scene:
        shown_scene = scene
        previous.blit(screen, 0, 0)
        fade_left = FADE_TIME
        if weathercode not in SNOW_LEVELS:
            for i in range(SETTLE_COLUMNS):
                snow_depth[i] = 0
            settle_in = 0

    # clear the display
    screen.pen = color.rgb(0, 0, 0)
    screen.clear()

    # we set the font and AA level here
    # to make sure it's set properly when coming in from another plugin
    screen.font = font.ignore
    screen.antialias = image.X4

    now = time.ticks_ms() / 1000
    # seconds since the last frame. ticks_ms wraps after about 12 days,
    # which gives one negative step
    elapsed = min(max(now - last, 0), 0.25)
    last = now

    if has_location:
        if temperature is not None:

            screen.pen = color.white
            cloud_at += vec2(cloud_drift, 0) * elapsed

            # weather codes from https://open-meteo.com/en/docs
            if weathercode in SNOW_LEVELS:
                draw_cloud_band()
                screen.pen = snowy_bg
                screen.clear()
                draw_snow(now, elapsed, SNOW_LEVELS[weathercode])
            elif weathercode in RAIN_LEVELS:
                draw_cloud_band()
                screen.pen = rainy_bg
                screen.clear()
                draw_rainy(elapsed, RAIN_LEVELS[weathercode])
            elif weathercode in [1, 2]:  # codes for mainly clear and partly cloudy
                if is_day:
                    screen.pen = sky_bg
                    screen.clear()
                    draw_sunny(now)
                else:
                    screen.pen = night_bg
                    screen.clear()
                    draw_moon(now)
                draw_light_cloud()
            elif weathercode in [45, 48]:  # codes for fog
                screen.pen = fog_bg
                screen.clear()
                # fog drifts at under half the speed of cloud
                fog.transform = mat3().translate(cloud_at * 0.4).scale(FOG_STRETCH, 1)
                screen.pen = fog
                screen.clear()
            elif weathercode in [3]:  # codes for overcast
                draw_overcast()
            elif weathercode in [0]:  # codes for clear sky
                if is_day:
                    screen.pen = sky_bg
                    screen.clear()
                    draw_sunny(now)
                else:
                    screen.pen = night_bg
                    screen.clear()
                    draw_moon(now)
            elif weathercode in STORM_CODES:
                draw_cloud_band()
                screen.pen = stormy_bg
                screen.clear()
                if weathercode in HAIL_LEVELS:
                    # lighter rain, so the hail stands out
                    draw_rainy(elapsed, RAIN)
                    screen.pen = HAIL_PEN
                    for i in range(HAIL_LEVELS[weathercode]):
                        stone = hail_particles[i]
                        stone[2] += HAIL_GRAVITY * elapsed
                        stone[1] += stone[2] * elapsed
                        if stone[1] >= HAIL_FLOOR:
                            if stone[3]:
                                # landed after its bounce, so it starts again at the top
                                stone[0] = randint(0, screen.width - 1)
                                stone[1] = 0
                                stone[2] = uniform(*HAIL_SPEED)
                                stone[3] = False
                            else:
                                stone[1] = HAIL_FLOOR
                                stone[2] = -stone[2] * HAIL_BOUNCE
                                stone[3] = True
                        screen.circle(stone[0], stone[1], HAIL_RADIUS)
                else:
                    draw_rainy(elapsed, HEAVY_RAIN)

            label = LABELS[weathercode]
            if weathercode == 0 and not is_day:
                label = "Clear"

            # clear skies have their own night scene, the rest are darkened
            if not is_day and weathercode not in [0, 1, 2]:
                screen.pen = fog_night_overlay if weathercode in [45, 48] else night_overlay
                screen.rectangle(0, 0, screen.width, screen.height)

            if weathercode in [0, 1, 2]:
                # local minutes past midnight. the board's clock is utc
                minute = (time.time() + utc_offset) // 60 % 1440
                nearest = min(abs(minute - sunrise_minute), abs(minute - sunset_minute))
                warmth = 1 - nearest / GLOW_MINUTES
                if warmth > 0:
                    screen.alpha = int(255 * warmth)
                    screen.pen = dusk_glow
                    screen.rectangle(0, 0, screen.width, screen.height)
                    screen.alpha = 255

            # after the night overlay, so it stays bright after dark
            if weathercode in STORM_CODES:
                strike_in -= elapsed
                since_strike += elapsed
                if strike_in <= 0:
                    strike_in = uniform(*STRIKE_GAP)
                    since_strike = 0
                    x = uniform(BOLT_MARGIN, screen.width - BOLT_MARGIN)
                    y = BOLT_TOP
                    bolt = [(x, y)]
                    for _ in range(BOLT_STEPS):
                        x += uniform(-BOLT_JITTER, BOLT_JITTER)
                        y += uniform(*BOLT_STEP_DOWN)
                        bolt.append((x, y))

                glow = 0
                for start, length, strength in FLASHES:
                    if start <= since_strike < start + length:
                        glow = strength * (1 - (since_strike - start) / length)
                if glow > 0:
                    screen.alpha = int(255 * glow)
                    screen.pen = flash_glow
                    screen.rectangle(0, 0, screen.width, CLOUD_BASE)
                    screen.pen = color.white
                    for i in range(BOLT_STEPS):
                        screen.line(bolt[i][0], bolt[i][1], bolt[i + 1][0], bolt[i + 1][1])
                    screen.alpha = 255

            shadow = SNOW_TEXT_SHADOW if weathercode in SNOW_LEVELS else TEXT_SHADOW
            centre_text(label, cy=(screen.height - 17), max_size=1, shadow=shadow)

            # draw the temperature, centre stage.
            centre_text(f"{temperature}°", cy=CY - 15, shadow=shadow)
        else:
            screen.pen = sky_bg
            screen.clear()
            centre_text("Loading", max_size=1)
    else:
        draw_qr_screen("Weather", "Setup needed", "weather")

    if fade_left > 0:
        fade_left -= elapsed
        screen.alpha = int(255 * max(fade_left, 0) / FADE_TIME)
        screen.blit(previous, 0, 0)
        screen.alpha = 255
