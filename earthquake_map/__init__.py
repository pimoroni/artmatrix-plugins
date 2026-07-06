import json
import math
import time
from fetch import AsyncFetch
from scrolling import Scroll

cx = screen.width // 2
cy = screen.height // 2
s = 1.5
target_s = 1.5

cam_lon = -122.055
cam_lat = 37.837

screen.antialias = image.X4

HOST = "earthquake.usgs.gov"
PATH = "/fdsnws/event/1/query?format=geojson&limit=10&orderby=time&minmagnitude=4"
GEOJSON_FILE = "/lib/plugins/iss_tracker/world.geo.json"

screen.font = rom_font.sins

coastline_data = []

quakes = []
quake_index = 0
quake_lon = -122.055
quake_lat = 37.837
quake_mag = 0.0
quake_place = "Connecting..."

last_cycle_time = time.ticks_ms()
CYCLE_INTERVAL_MS = 10000
scroll_obj = None

api = AsyncFetch(HOST, 443, use_tls=True, debug=True)


@api.on_complete
def handle_response(fetch_instance):
    global quakes, quake_index, quake_lon, quake_lat, quake_mag, quake_place, last_cycle_time, scroll_obj
    try:
        data = fetch_instance.to_json()
        if data and "features" in data and len(data["features"]) > 0:
            quakes = []
            for feature in data["features"]:
                props = feature["properties"]
                coords = feature["geometry"]["coordinates"]
                quakes.append({"mag": props["mag"], "place": props["place"], "lon": float(coords[0]), "lat": float(coords[1])})

            if quake_index >= len(quakes):
                quake_index = 0

            active = quakes[quake_index]
            quake_mag = active["mag"]
            quake_place = active["place"]
            quake_lon = active["lon"]
            quake_lat = active["lat"]
            last_cycle_time = time.ticks_ms()

            scroll_obj = None

        else:
            quake_place = "No Data Found"
    except Exception:
        quake_place = "Parse Error"


def load_coastlines():
    global quake_place
    try:
        with open(GEOJSON_FILE, "r") as f:
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

                    country_center = (mn + mx) * 0.5
                    lat_zone = (lat_mx + lat_mn) * 0.5

                    if abs(lat_zone) > 60:
                        pen_color = color.white
                    elif -22 <= lat_zone <= 10:
                        pen_color = color.yellow
                    else:
                        pen_color = color.lime

                    coastline_data.append((shape.custom(path), country_center, pen_color))

    except Exception:
        quake_place = "Map Load Error"


load_coastlines()
api.fetch(PATH, interval=60)


def draw_unselected_quakes():
    screen.pen = color.rgb(130, 0, 0, 200)
    for idx, q in enumerate(quakes):
        if idx == quake_index:
            continue

        dlon = q["lon"] - cam_lon
        if dlon > 180:
            dlon -= 360
        if dlon < -180:
            dlon += 360
        dlat = q["lat"] - cam_lat

        qx = int(cx + (dlon * s))
        qy = int(cy - (dlat * s * 1.3))

        if 0 <= qx < screen.width and 0 <= qy < screen.height:
            screen.shape(shape.circle(vec2(qx, qy), 1.5))


def draw_epicenter_reticle():
    loop_duration = 2000
    max_geo_radius = 25
    stroke_width = max(2, int(2.0 * s))

    dlon = quake_lon - cam_lon
    if dlon > 180:
        dlon -= 360
    if dlon < -180:
        dlon += 360
    dlat = quake_lat - cam_lat

    ex = int(cx + (dlon * s))
    ey = int(cy - (dlat * s * 1.3))

    for ring_index in range(3):
        stagger_ms = ring_index * (loop_duration // 3)
        current_time = (time.ticks_ms() + stagger_ms) % loop_duration
        progress = current_time / loop_duration

        geo_radius = progress * max_geo_radius
        ring_radius = geo_radius * s

        if ring_radius > 4:
            alpha_val = int(((1.0 - progress) ** 2) * 255)
            screen.pen = color.rgb(255, 0, 0, alpha_val)
            radar_ring = shape.circle(vec2(ex, ey), ring_radius).stroke(stroke_width)
            screen.shape(radar_ring)

    pulse_angle = (time.ticks_ms() / 1000) * (2 * math.pi)
    pulse_base = (math.sin(pulse_angle) * 1.0) + 2.5
    pulse_radius = int(pulse_base * min(s, 2.5))

    screen.pen = color.rgb(255, 0, 0, 255)
    screen.shape(shape.circle(vec2(ex, ey), max(3, pulse_radius)))

    screen.pen = color.rgb(255, 255, 255, 255)
    screen.shape(shape.circle(vec2(ex, ey), 1))


def draw_map_view():
    base_ty = (cam_lat * s * 1.3) + cy

    inv_360 = 1 / 360
    local_floor = math.floor

    for coastline_shape, center, pen_color in coastline_data:
        o = 360 * local_floor((cam_lon - center) * inv_360 + 0.5)
        tx = ((o - cam_lon) * s) + cx

        screen.pen = pen_color

        coastline_shape.transform = mat3().translate(tx, base_ty).scale(s, s * 1.3)
        screen.shape(coastline_shape)

    draw_unselected_quakes()
    draw_epicenter_reticle()

    screen.pen = color.rgb(0, 0, 0, 160)
    screen.shape(shape.rectangle(0, screen.height - 10, screen.width, 10))


def draw_status_indicator():
    if api.status == api.FETCHING:
        angle = time.ticks_ms() / 50
        ix = int((screen.width - 8) + math.cos(angle) * 3)
        iy = int(6 + math.sin(angle) * 3)
        screen.pen = color.yellow
        screen.shape(shape.circle(vec2(ix, iy), 2))


def update():
    global s, target_s, quake_index, quake_lon, quake_lat, quake_mag, quake_place
    global cam_lon, cam_lat, last_cycle_time
    global scroll_obj

    screen.pen = color.navy
    screen.clear()

    if scroll_obj is None:
        scroll_obj = Scroll(f"{quake_place}", align="bottom")

    api.update()

    if len(quakes) > 0 and time.ticks_diff(time.ticks_ms(), last_cycle_time) > CYCLE_INTERVAL_MS:
        quake_index = (quake_index + 1) % len(quakes)
        active = quakes[quake_index]
        quake_mag = active["mag"]
        quake_place = active["place"]
        quake_lon = active["lon"]
        quake_lat = active["lat"]
        last_cycle_time = time.ticks_ms()
        scroll_obj = None

    # Calculate short-path longitudinal distance
    dlon = quake_lon - cam_lon
    if dlon > 180:
        dlon -= 360
    if dlon < -180:
        dlon += 360

    dlat = quake_lat - cam_lat

    distance = math.sqrt(dlon**2 + dlat**2)

    # When distance is close to 0, target_s approaches 1.8.
    # When distance is large (>15), target_s smoothly scales down to 1.1.
    target_s = 1.1 + (0.7 / (1.0 + math.exp((distance - 10.0) * 0.4)))

    # Slightly easing the position tracking relative to zoom keeps them in phase
    s += (target_s - s) * 0.08
    cam_lon += dlon * 0.06
    cam_lat += dlat * 0.06
    cam_lon = ((cam_lon + 180) % 360) - 180

    draw_map_view()
    draw_status_indicator()

    if scroll_obj:
        scroll_obj.update()
        screen.pen = color.white
        scroll_obj.render()
