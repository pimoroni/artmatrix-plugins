import time
from fetch import AsyncFetch, HTTPException
import math
from random import randint, uniform

from plugin_config import plugin_config

CX = screen.width / 2
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

snowy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(109, 129, 150)), (1.0, color.rgb(198, 205, 212))))
rainy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(105, 105, 105)), (1.0, color.rgb(80, 123, 156))))
stormy_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height, ((0.0, color.rgb(105, 105, 105)), (1.0, color.rgb(70, 70, 70))))
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

sun_grad = brush.gradient(brush.RADIAL, 15, 15, 0, 0, ((0.0, color.rgb(255, 210, 120)), (1.0, color.rgb(255, 180, 40))))


# Create the rain_particles list
rain_particles = []
for _ in range(100):
    x = randint(1, screen.width - 1)
    y = randint(0, screen.height - 1)
    speed = uniform(0.7, 1.0)
    size = randint(1, 3)
    rain_particles.append([x, y, speed, size])


# Create the rain_particles list
snow_particles = []
for _ in range(100):
    x = randint(1, screen.width - 1)
    y = randint(0, screen.height - 1)
    speed = uniform(0.1, 0.4)
    size = 1
    offset = uniform(1, 6.0)
    snow_particles.append([x, y, speed, size, offset])


def draw_rainy(_t):
    screen.pen = color.rgb(255, 255, 255, 70)
    # Background rain_particles
    for p in rain_particles:
        p[1] += p[2]
        if p[1] > screen.height - 4:
            p[1] = 0
            p[0] = randint(1, screen.width - 1)

        screen.rectangle(p[0], p[1], 1, 4)


def draw_snow(t):
    screen.pen = color.rgb(255, 255, 255, 170)
    # Background rain_particles
    for p in snow_particles:
        p[1] += p[2]
        if p[1] > screen.height - 4:
            p[1] = 0
            p[0] = randint(1, screen.width - 1)

        screen.circle(p[0] + (math.sin(t + p[4]) * 6), p[1], p[3])


def draw_sunny(t):
    centre = vec2(15, 15)
    sun_radius = 15
    rays = 50
    ray_a = 360 / rays
    rotate = t * 5

    screen.pen = color.rgb(255, 255, 255)
    for i in range(rays):
        a = (ray_a * i) + rotate
        b = a + ray_a
        screen.alpha = 90 if i & 1 else 40
        screen.shape(shape.pie(vec2(centre.x, centre.y), 160, a, b))

    screen.alpha = 255
    screen.pen = sun_grad
    screen.circle(centre.x, centre.y, sun_radius)


cloud_at = vec2(0.0, 0.0)
last = 0


def draw_overcast(t):
    global cloud_at, last

    now = t
    dt = now - last
    last = now
    if dt > 0.25:
        dt = 0.25

    cloud_at += vec2(10, 0) * dt
    over_cloud.transform = mat3().translate(cloud_at)
    screen.pen = over_cloud
    screen.clear()


def draw_light_cloud(t):
    global cloud_at, last

    now = t
    dt = now - last
    last = now
    if dt > 0.25:
        dt = 0.25

    cloud_at += vec2(10, 0) * dt
    light_cloud.transform = mat3().translate(cloud_at)
    screen.pen = light_cloud
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
        global weathercode, temperature

        data = fetch.to_json()

        current = data["current_weather"]
        temperature = round(current["temperature"])
        weathercode = current["weathercode"]

    @api_data.on_error
    def error(fetch):
        print("HTTP", fetch.http_status, fetch.stream.read())
        api_data.fetch(API_PATH, interval=UPDATE_INTERVAL)


def update():

    # clear the display
    screen.pen = color.rgb(0, 0, 0)
    screen.clear()

    # we set the font and AA level here
    # to make sure it's set properly when coming in from another plugin
    screen.font = font.ignore
    screen.antialias = image.X4

    t = time.ticks_ms() / 1000

    if has_location:

        try:
            api_data.update()
        except HTTPException:
            pass

        if temperature is not None:

            screen.pen = color.white

            # Weather codes from https://open-meteo.com/en/docs
            if weathercode in [71, 73, 75, 77, 85, 86]:  # codes for snow
                screen.pen = snowy_bg
                screen.clear()
                draw_snow(t)
                centre_text("Snowy", cy=(screen.height - 17), max_size=1)
            elif weathercode in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]:  # codes for rain
                screen.pen = rainy_bg
                screen.clear()
                draw_rainy(t)
                centre_text("Rainy", cy=(screen.height - 17), max_size=1)
            elif weathercode in [1, 2]:  # codes for partly cloudy   3, 45, 48
                screen.pen = sky_bg
                screen.clear()
                draw_light_cloud(t)
                centre_text("Cloudy", cy=(screen.height - 17), max_size=1)
            elif weathercode in [3, 45, 48]:  # codes for overcast/heavy cloud
                draw_overcast(t)
                centre_text("Overcast", cy=(screen.height - 17), max_size=1)
            elif weathercode in [0]:  # codes for sun
                screen.pen = sky_bg
                screen.clear()
                draw_sunny(t)
                centre_text("Sunny", cy=(screen.height - 17), max_size=1)
            elif weathercode in [95, 96, 99]:  # codes for storm
                screen.pen = stormy_bg
                screen.clear()
                draw_rainy(t)
                centre_text("Stormy", cy=(screen.height - 17), max_size=1)

            # draw the temperature, centre stage.
            centre_text(f"{temperature}°", cy=CY - 15)
    else:
        screen.font = font.salty
        screen.pen = rainy_bg
        screen.clear()
        draw_rainy(t)
        centre_text("Setup needed", CY - 50)
        centre_text("visit", CY - 10, 1)
        centre_text("artmatrix.local", CY + 5, 2)
        centre_text("to configure", CY + 40, 1)
        centre_text("plugin", CY + 50, 1)
