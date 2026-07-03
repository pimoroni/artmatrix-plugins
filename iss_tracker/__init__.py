import json
import math
from datetime import datetime, timezone
import time
from fetch import AsyncFetch, HTTPException

screen.font = rom_font.sins

CX, CY = screen.width / 2, screen.height / 2

API_HOST = "api.open-notify.org"
ISS_JSON = "/iss-now.json"

UPDATE_INTERVAL = 60

MAP_HEIGHT = 180
MAP_WIDTH = 360
PATH_WIDTH = 2

STAR_PATTERN = brush.pattern(color.rgb(0, 0, 0), color.grey, 20)
BORDER_PATTERN = brush.pattern(color.white, color.rgb(0, 0, 0), 25)
SEA_PATTERN = brush.pattern(color.navy, color.rgb(255, 255, 255, 140), 32)
NIGHT_COLOR = color.rgb(0, 0, 0, 64)

coastlines = []
coastline_bounds = []
coastline_lats = []
iss_path = []
long, lat = None, None

iss_sprite = image.load("lib/plugins/iss_tracker/icon.png")

api_data = AsyncFetch(API_HOST, 80, use_tls=False, debug=True)
api_data.fetch(f"{ISS_JSON}", interval=UPDATE_INTERVAL)


@api_data.on_complete
def complete(fetch):
    global long, lat, x, y

    j = fetch.to_json()
    long, lat = float(j["iss_position"]["longitude"]), float(j["iss_position"]["latitude"])

    if long and lat:
        x, y = -long, lat

        # add location to list and clamp it to max length of 90
        iss_path.append((-x, -y))
        if len(iss_path) > 90:
            iss_path.pop(0)

    # start the load for the NEXT location
    api_data.fetch(f"{ISS_JSON}")


@api_data.on_error
def error(fetch):
    print(fetch.http_status, fetch.http_response_headers)

    # start the load for the NEXT location
    api_data.fetch(f"{ISS_JSON}", interval=UPDATE_INTERVAL)


def load_coastlines():

    with open("lib/plugins/iss_tracker/world.geo.json", "r") as f:
        data = json.loads(f.read())
        for country in data:
            for polygon in country["polygons"]:
                mn = 180
                mx = -180
                lat_mn = 90
                lat_mx = -90
                path = []
                for p in polygon:
                    path.append(vec2(p[0], -p[1]))
                    mn = min(mn, p[0])
                    mx = max(mx, p[0])
                    lat_mn = min(lat_mn, -p[1])
                    lat_mx = max(lat_mx, -p[1])

                coastline_lats.append((lat_mx + lat_mx) / 2)
                coastlines.append(shape.custom(path))
                coastline_bounds.append((mn, mx))


def get_tau_and_dec():

    dt = datetime.now(timezone.utc)
    year = dt.year
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    days_into_year = (dt - start).total_seconds() / 86400

    seconds_since_midnight = dt.hour * 3600 + dt.minute * 60 + dt.second
    degrees = (seconds_since_midnight / 86400) * 360  # 86400 seconds in a day

    declination = -23.45 * math.cos(math.radians((360 / 365) * (days_into_year + 10)))
    return degrees - 180, declination


load_coastlines()

# starting points for the x and y
x, y = 0, 0

# scale value
s = 1.5


def calc_day_night_latitude(longitude, dec):
    latitude = 0
    cos_lat = math.cos(math.radians(longitude))
    try:
        tan_lat = -cos_lat / math.tan(math.radians(dec))
        latitude = math.degrees(math.atan(tan_lat))
    except ZeroDivisionError:
        latitude = 90.0 if cos_lat > 0 else -90.0 if cos_lat < 0 else 0
    return latitude


def draw_notification(t):
    w, _ = screen.measure_text(t)
    screen.pen = color.rgb(0, 0, 0, 100)
    screen.rectangle(8, 10, w + 30, 15)
    screen.pen = color.white
    screen.text(t, 10, 11)


def draw_map():

    matricies = []
    cx_scaled = CX / s
    y_scaled = y * s

    tau, dec = get_tau_and_dec()

    for o in [-360, 0, 360]:
        matricies.append(mat3().translate(((x + o) * s) + CX, y_scaled + CY).scale(s, s))

    daynight = []
    daynight.append(vec2(-180, 90))
    for i in range(-180, 180 + 1, 1):
        lat = calc_day_night_latitude(i + tau, dec)
        daynight.append(vec2(i, -lat))
    daynight.append(vec2(180, 90))
    daynight_shape = shape.custom(daynight)

    screen.pen = SEA_PATTERN
    screen.rectangle(0, y_scaled + CY - (90 * s), screen.width, 180 * s)

    for i, coastline in enumerate(coastlines):
        mn, mx = coastline_bounds[i]
        if abs(coastline_lats[i]) > 60:
            screen.pen = color.white
        elif coastline_lats[i] >= -22 and coastline_lats[i] <= 10:
            screen.pen = color.yellow
        else:
            screen.pen = color.lime
        for j, o in enumerate([-360, 0, 360]):
            if mn + o < -x + cx_scaled or mx + o > -x - cx_scaled:
                coastline.transform = matricies[j]
                screen.shape(coastline)

    screen.pen = NIGHT_COLOR
    for j, o in enumerate([-360, 0, 360]):
        if -180 + o < -x + cx_scaled or 180 + o > -x - cx_scaled:
            daynight_shape.transform = matricies[j]
            screen.shape(daynight_shape)

    screen.pen = color.white
    if len(iss_path) > 0:
        x1, y1 = iss_path[0]
        for i in range(1, len(iss_path)):
            x2, y2 = iss_path[i]
            if x2 < x1:
                x1 -= 360
            line_seg = shape.line(x1, y1, x2, y2, PATH_WIDTH / s)
            for j, o in enumerate([-360, 0, 360]):
                if x1 + o < -x + cx_scaled or x2 + o > -x - cx_scaled:
                    line_seg.transform = matricies[j]
                    screen.shape(line_seg)
            x1, y1 = x2, y2

        w, h = iss_sprite.width, iss_sprite.height
        i = (math.sin(time.time() / 120) * 64) + (255 - 64)
        screen.alpha = int(i)
        screen.blit(iss_sprite, vec2(CX - (w / 2), CY - (h / 2)))
        screen.alpha = 255


def update():

    try:
        api_data.update()
    except HTTPException as e:
        print("Exception was raised!")
        print(e.fetch.http_status)
    except OSError:
        pass

    screen.pen = STAR_PATTERN
    screen.clear()

    draw_map()
