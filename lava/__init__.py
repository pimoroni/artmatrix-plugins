import time
import random
from array import array
from plugins.lava import colorsys
from plugin_config import plugin_config

width = screen.width
height = screen.height
screen.antialias = image.X4


# These variables are exposed to the editor.
cfg = plugin_config("lava", {
    "num_blobs": 4,
    "rainbow_mode": False,  # Switches between mainly a single hue brightening at the centre and moving slightly colder at the edge, and a hue constantly changing with radius.
    "start_colour": (255, 255, 0),  # Defines the main colour in single-colour mode, or the central colour in rainbow mode.
    "min_radius": 10,  # Minimum blob radius, roughly but not exactly in number of pixels
    "max_radius": 20,  # Maximum blob radius, same
})
num_blobs = cfg["num_blobs"]
rainbow_mode = cfg["rainbow_mode"]
start_colour = cfg["start_colour"]
min_radius = cfg["min_radius"]
max_radius = cfg["max_radius"]


def clamp(v, maxval, minval):
    return max(minval, min(maxval, v))


def make_colour(colour, delta):
    h, s, v = colour
    dh, ds, dv = delta

    nh = h + dh
    while nh > 1:
        nh -= 1
    while nh < 0:
        nh += 1

    ns = clamp(s * ds, 1, 0)
    nv = clamp(v * dv, 1, 0)

    r, g, b = colorsys.hsv_to_rgb(nh, ns, nv)
    r = int(r * 255)
    g = int(g * 255)
    b = int(b * 255)
    return (r, g, b)


def convert_to_rgba(r, g, b):
    return 0xff000000 | (b << 16) | (g << 8) | r


@micropython.native
def colour_lerp(colour1, colour2, t):
    r = colour1[0] + ((colour2[0] - colour1[0]) * t)
    g = colour1[1] + ((colour2[1] - colour1[1]) * t)
    b = colour1[2] + ((colour2[2] - colour1[2]) * t)

    return (r, g, b)


def colour_picker(p, edge_falloff):
    if p <= 0.1:
        r, g, b = colour_lerp(colour_1, colour_2, p / 0.1)
    elif p > 0.1 and p <= 0.2:
        r, g, b = colour_lerp(colour_2, colour_3, (p - 0.1) / 0.1)
    elif p > 0.2 and p <= 0.4:
        r, g, b = colour_lerp(colour_3, colour_4, (p - 0.2) / 0.2)
    elif p > 0.4 and p <= 0.95:
        r, g, b = colour_lerp(colour_4, colour_5, (p - 0.4) / 0.55)
    else:
        r, g, b = colour_5

    r *= edge_falloff
    g *= edge_falloff
    b *= edge_falloff

    return (int(r), int(g), int(b))


@micropython.native
def generate_palette_stop(i):
    edge_falloff = (i - 128) ** 2
    if edge_falloff > 255:
        edge_falloff = 255
    edge_falloff /= 255

    if i == 0:
        val = 255
    else:
        val = 4 / i
        val /= 0.03
        val = 1 - val

    if i < 128:
        return (0, 0, 0)

    return colour_picker(val, edge_falloff)


@micropython.viper
def render(width: int, height: int, num_blobs: int):
    destination = ptr32(screen)
    palette = ptr32(raw_palette)
    blob_x = ptr32(blob_x_array)
    blob_y = ptr32(blob_y_array)
    blob_radius = ptr32(blob_radius_array)
    i = 0

    for y in range(height):
        for x in range(width):
            weight = (1800 // (height - y)) + (1800 // (y + 1))
            for blob in range(num_blobs):
                dx = x - int(blob_x[blob])
                dy = y - int(blob_y[blob])
                weight += (blob_radius[blob] * blob_radius[blob]) // ((dx * dx + dy * dy + 8) >> 3)   # +1 avoids /0 at the centre
            if weight > 8000:
                weight = 8000
            destination[i] = palette[weight]
            i += 1


def move_blobs():
    if num_blobs > 0:
        for blob in range(num_blobs - 1, -1, -1):
            y = blob_y_array[blob]
            radius = blob_radius_array[blob]
            max_radius = blob_max_radius_array[blob]
            velocity = blob_velocity_array[blob]

            if y == 0 and velocity == 0:
                if radius < max_radius:
                    blob_radius_array[blob] = blob_radius_array[blob] + 1
                else:
                    blob_velocity_array[blob] = 1
            elif y == height and velocity == 0:
                if radius < max_radius:
                    blob_radius_array[blob] = radius + 1
                else:
                    blob_velocity_array[blob] = -1
            elif y < -(2 * max_radius) or y > (height + (2 * max_radius)):
                blob_x_array[blob] = random.randint(0, width)
                blob_y_array[blob] = height * random.randint(0, 1)
                blob_radius_array[blob] = 1
                blob_max_radius_array[blob] = random.randint(min_radius_adjusted, max_radius_adjusted)
                blob_velocity_array[blob] = 0

            blob_y_array[blob] = blob_y_array[blob] + int(blob_velocity_array[blob])


h, s, v = colorsys.rgb_to_hsv(start_colour[0] / 255, start_colour[1] / 255, start_colour[2] / 255)

if rainbow_mode:
    colour_1 = make_colour((h, s, v), (-0.8, 1, 1))
    colour_2 = make_colour((h, s, v), (-0.6, 1, 1))
    colour_3 = make_colour((h, s, v), (-0.4, 1, 1))
    colour_4 = make_colour((h, s, v), (-0.2, 1, 1))
    colour_5 = make_colour((h, s, v), (0, 1, 1))
else:
    colour_1 = make_colour((h, s, v), (-0.15, 1, 0.4))
    colour_2 = make_colour((h, s, v), (-0.1, 1, 0.6))
    colour_3 = make_colour((h, s, v), (-0.05, 1, 0.8))
    colour_4 = make_colour((h, s, v), (0, 1, 1))
    colour_5 = make_colour((h, s, v), (0.05, 0.3, 1))

raw_palette = array("i", [convert_to_rgba(*generate_palette_stop(j)) for j in range(8000)])
min_radius_adjusted = int((min_radius + 0.7236) / 0.2564)
max_radius_adjusted = int((max_radius + 0.7236) / 0.2564)
blob_x_array = array("i")
blob_y_array = array("i")
blob_radius_array = array("i")
blob_max_radius_array = array("i")
blob_velocity_array = array("f")

for _ in range(num_blobs):
    blob_x_array.append(random.randint(0, width))
    blob_y_array.append(height * random.randint(0, 1))
    blob_radius_array.append(1)
    blob_max_radius_array.append(random.randint(min_radius_adjusted, max_radius_adjusted))
    blob_velocity_array.append(0)

last_frame = 0


def update():
    global last_frame
    now = time.ticks_ms()
    elapsed = now - last_frame
    if elapsed > 33:
        move_blobs()
        render(width, height, num_blobs)
        last_frame = now
