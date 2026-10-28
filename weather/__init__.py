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
})
lat = cfg["lat"]
long = cfg["lng"]
if lat is not None:
    lat = float(lat)
if long is not None:
    long = float(long)


has_location = True
if None in (lat, long):
    has_location = False

API_HOST = "api.open-meteo.com"
API_PATH = f"/v1/forecast?latitude={lat}&longitude={long}&current_weather=true&timezone=auto"
UPDATE_INTERVAL = 600   # 10 minutes

weathercode = None
temperature = None
is_day = None
# from the wind. cloud and snow drift in px a second, rain in px sideways per px of fall
cloud_drift = None
snow_drift = None
rain_slant = None

# rain, snow and storms have cloud above CLOUD_BASE. their background is clear down
# to CLOUD_FADE_START of the screen, then fades in to solid at CLOUD_BASE
CLOUD_BASE = 58
CLOUD_FADE_START = 0.15
CLOUD_FADE_END = CLOUD_BASE / screen.height

snowy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(109, 129, 150, 0)), (CLOUD_FADE_START, color.rgb(109, 129, 150, 0)), (CLOUD_FADE_END, color.rgb(109, 129, 150)), (1.0, color.rgb(198, 205, 212))))
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

night_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(6, 10, 30)), (1.0, color.rgb(28, 40, 78))))

# laid over the cloudy, wet and foggy scenes after dark
night_overlay = color.rgb(6, 10, 30, 150)

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

# snow levels: flakes drawn, and whether a third of them are big near ones
LIGHT_SNOW = (60, True)
SNOW = (100, True)
HEAVY_SNOW = (150, True)
SNOW_GRAINS = (100, False)
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
    flakes, big_flakes = level
    for i in range(flakes):
        flake = snow_particles[i]
        layer = flake[2] if big_flakes else 0
        radius, _, pen = SNOW_LAYERS[layer]
        flake[1] += flake[3] * elapsed
        flake[0] = (flake[0] + snow_drift * elapsed) % screen.width
        if flake[1] > screen.height:
            flake[1] = 0
            flake[0] = randint(0, screen.width - 1)

        screen.pen = pen
        screen.circle(flake[0] + math.sin(now + flake[4]) * SNOW_SWAY, flake[1], radius)


def draw_sunny(now):
    centre = vec2(15, 15)
    sun_radius = 15
    rays = 50
    ray_a = 360 / rays
    rotate = now * 5

    screen.pen = color.rgb(255, 255, 255)
    for i in range(rays):
        a = (ray_a * i) + rotate
        b = a + ray_a
        screen.alpha = 90 if i & 1 else 40
        screen.shape(shape.pie(vec2(centre.x, centre.y), 160, a, b))

    screen.alpha = 255
    screen.pen = sun_grad
    screen.circle(centre.x, centre.y, sun_radius)


def draw_moon(now):
    for x, y, phase in stars:
        brightness = 110 + int(math.sin(now * 1.5 + phase) * 80)
        screen.pen = color.rgb(255, 255, 255, brightness)
        screen.rectangle(x, y, 1, 1)

    screen.pen = moon_halo
    screen.circle(MOON_X, MOON_Y, MOON_HALO_RADIUS)
    screen.pen = moon_craters
    screen.circle(MOON_X, MOON_Y, MOON_RADIUS)


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


def centre_text(text, cy=None, max_size=12, min_size=1, padding=4, colour=color.white):

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

    screen.pen = color.rgb(0, 0, 0, 100)
    screen.text(text, vec2((cx - tw / 2) + 2, (cy - th / 2) + 2), size)

    screen.pen = colour
    screen.text(text, vec2(cx - tw / 2, cy - th / 2), size)


if has_location:
    api_data = AsyncFetch(API_HOST, debug=True)
    api_data.fetch(API_PATH, interval=UPDATE_INTERVAL)

    @api_data.on_complete
    def complete(fetch):
        global weathercode, temperature, is_day, cloud_drift, snow_drift, rain_slant

        data = fetch.to_json()

        current = data["current_weather"]
        temperature = round(current["temperature"])
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
    global cloud_at, last, strike_in, since_strike, bolt

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

        try:
            api_data.update()
        except HTTPException:
            pass

        if temperature is not None:

            screen.pen = color.white
            cloud_at += vec2(cloud_drift, 0) * elapsed

            # weather codes from https://open-meteo.com/en/docs
            if weathercode in SNOW_LEVELS:
                draw_cloud_band()
                screen.pen = snowy_bg
                screen.clear()
                draw_snow(now, elapsed, SNOW_LEVELS[weathercode])
                label = "Snowy"
            elif weathercode in RAIN_LEVELS:
                draw_cloud_band()
                screen.pen = rainy_bg
                screen.clear()
                draw_rainy(elapsed, RAIN_LEVELS[weathercode])
                label = "Rainy"
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
                label = "Cloudy"
            elif weathercode in [45, 48]:  # codes for fog
                screen.pen = fog_bg
                screen.clear()
                # fog drifts at under half the speed of cloud
                fog.transform = mat3().translate(cloud_at * 0.4).scale(FOG_STRETCH, 1)
                screen.pen = fog
                screen.clear()
                label = "Foggy"
            elif weathercode in [3]:  # codes for overcast
                draw_overcast()
                label = "Overcast"
            elif weathercode in [0]:  # codes for clear sky
                if is_day:
                    screen.pen = sky_bg
                    screen.clear()
                    draw_sunny(now)
                    label = "Sunny"
                else:
                    screen.pen = night_bg
                    screen.clear()
                    draw_moon(now)
                    label = "Clear"
            elif weathercode in STORM_CODES:
                draw_cloud_band()
                screen.pen = stormy_bg
                screen.clear()
                draw_rainy(elapsed, HEAVY_RAIN)
                label = "Stormy"

            # clear skies have their own night scene, the rest are darkened
            if not is_day and weathercode not in [0, 1, 2]:
                screen.pen = night_overlay
                screen.rectangle(0, 0, screen.width, screen.height)

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

            centre_text(label, cy=(screen.height - 17), max_size=1)

            # draw the temperature, centre stage.
            centre_text(f"{temperature}°", cy=CY - 15)
        else:
            screen.pen = sky_bg
            screen.clear()
            centre_text("Loading", max_size=1)
    else:
        draw_qr_screen("Weather", "Setup needed", "weather")
