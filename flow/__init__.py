import math
import time
from array import array
from random import random

import micropython
from micropython import const

from plugin_config import plugin_config

# a painting of the wind. motes drift on a field of winds that swirl round the
# highs and lows of a random stream, so they never pile up or thin out.
#
# now and then the stream eases toward a new one. under it all a gentle wind
# slowly veers round and surges in gusts.
#
# each mote paints a stroke that swells in and tapers off. it's brighter and
# paler where the wind is quick. the colours drift from icy blues to golds and
# reds and back, or each mote takes a colour from a fixed scheme.
cfg = plugin_config("flow", {
    "colours": "wander",  # wander, or one of SCHEMES
    "mood": "breezy",  # one of MOODS
})
colours = cfg["colours"]
mood = cfg["mood"]

# the layers of motes, back to front. a sparse layer of bold, fast strokes
# moves over a dense one of fine, slow, dim ones
LAYERS = (
    # count, pace against the wind, stroke width px, solid /256, brightness 0 to 1
    (220, 0.6, 1.0, 150, 0.55),  # fine
    (70, 1.4, 2.2, 230, 1.0),  # bold
)
# frames a stroke swells in over, and tapers off over
TAPER = 20

# the wind field is FIELD x FIELD cells, worked out every FIELD_EVERY frames.
# under the swirls a gentle wind blows at PREVAILING px a frame. it takes VEER
# seconds to veer all the way round. EASE is how far the stream moves toward
# the next one each second
FIELD = 16
FIELD_EVERY = 4
PREVAILING = 0.25
EASE = 0.15
VEER = 600

# the wind's moods
MOODS = {
    # swirl speed px a frame and the most a gust adds. times the stream's
    # smoothed, broader the more. seconds between streams. trail kept each frame /256
    "calm": (0.45, 0.3, 4, 30, 249),
    "breezy": (0.7, 1.0, 3, 20, 244),
    "gusty": (1.1, 1.8, 2, 12, 236),
}
# unknown names fall back to breezy so the config page ticks what's showing
if mood not in MOODS:
    mood = "breezy"
SWIRL_SPEED, GUSTS, SMOOTHS, STREAM_SECONDS, TRAIL_KEEP = MOODS[mood]

# the sky, top and bottom
SKY_TOP = (8, 12, 30)
SKY_BOTTOM = (34, 24, 50)

# the colours wander along WARMTH and back over WANDER seconds. each mote gets
# one of SHADES, spread a little either side
WANDER = 240
SHADES = 11
# fixed schemes, each mote taking one of a scheme's colours. at most SHADES
# each. wander is the drift along WARMTH instead
SCHEMES = {
    "wander": None,
    "mixed": ((233, 90, 70), (244, 162, 97), (233, 196, 106), (42, 170, 150), (90, 160, 225),
              (150, 105, 200), (240, 236, 225)),
    "ice": ((200, 230, 255), (140, 200, 255), (90, 160, 235), (60, 120, 210), (170, 215, 240),
            (230, 245, 255)),
    "ember": ((255, 90, 40), (255, 140, 50), (255, 190, 80), (230, 60, 50), (255, 220, 140),
              (200, 50, 30)),
    "mono": ((255, 255, 255), (225, 225, 230), (190, 190, 200), (150, 150, 160)),
}
# unknown names fall back to wander so the config page ticks what's showing
if colours not in SCHEMES:
    colours = "wander"
SCHEME = SCHEMES[colours]
# a scale of colours, as (warmth, colour)
WARMTH = (
    (-10, (190, 215, 255)), (0, (140, 200, 255)), (7, (70, 170, 230)),
    (13, (60, 205, 170)), (19, (225, 205, 90)), (25, (255, 140, 60)), (33, (255, 70, 90)),
)
# the colours slow and fast motes lean toward. the number is how far
SLOW = ((40, 60, 120), 0.35)
FAST = ((255, 250, 235), 0.45)

# 0xff000000, a pixel's alpha byte fully on, written signed for viper
OPAQUE = const(-16777216)

# the trails, painted over from frame to frame
CANVAS = bytearray(128 * 128 * 4)
canvas = image(128, 128, CANVAS)

# the sky colour each row fades toward, and the wind field across and down in
# 256ths of a px a frame
SKY = array("I", bytes(4 * 128))
FIELD_X = array("i", bytes(4 * FIELD * FIELD))
FIELD_Y = array("i", bytes(4 * FIELD * FIELD))
# per layer. four ints a mote: x and y in 256ths of a px, frames left and its
# whole life. a slow and a fast ink per shade. the style brush() reads
LAYER_PLACES = [array("i", bytes(16 * layer[0])) for layer in LAYERS]
LAYER_INKS = [array("I", bytes(8 * SHADES)) for layer in LAYERS]
LAYER_STYLES = [array("i", bytes(4 * 6)) for layer in LAYERS]
# the random state brush() uses
SEED = array("i", [time.ticks_ms() | 1])


# fades each px toward its row's sky, keeping keep 256ths of the difference
@micropython.viper
def fade(pixels: ptr32, sky: ptr32, keep: int):
    y = 0
    while y < 128:
        sky_colour = sky[y]
        sky_red = sky_colour & 255
        sky_green = (sky_colour >> 8) & 255
        sky_blue = (sky_colour >> 16) & 255
        i = y * 128
        row_end = i + 128
        while i < row_end:
            colour = pixels[i]
            red = (colour & 255) - sky_red
            green = ((colour >> 8) & 255) - sky_green
            blue = ((colour >> 16) & 255) - sky_blue
            # a shift rounds negatives down, which would leave them stuck one below the sky
            red = (red * keep) >> 8 if red >= 0 else -(((-red) * keep) >> 8)
            green = (green * keep) >> 8 if green >= 0 else -(((-green) * keep) >> 8)
            blue = (blue * keep) >> 8 if blue >= 0 else -(((-blue) * keep) >> 8)
            pixels[i] = OPAQUE | ((sky_blue + blue) << 16) | ((sky_green + green) << 8) | (sky_red + red)
            i += 1
        y += 1


# moves each of count motes on the wind field and paints its stroke, a soft
# edged disc. it's stamped halfway and at the end of each move so fast strokes
# stay whole.
#
# a stroke swells in and tapers off over the mote's life. its colour is
# between the mote's slow and fast inks, by its speed. a mote whose life runs
# out starts again somewhere random.
#
# style is pace against the field /256, radius in 256ths of a px, solid /256,
# the speed counted as quick in 256ths of a px a frame, swell frames and the
# shade count in inks
@micropython.viper
def brush(pixels: ptr32, places: ptr32, count: int, field_x: ptr32, field_y: ptr32,
          inks: ptr32, seed: ptr32, style: ptr32):
    pace = style[0]
    radius = style[1]
    solid = style[2]
    quick = style[3]
    ramp = style[4]
    shades = style[5]
    state = seed[0]
    mote = 0
    while mote < count:
        slot = mote * 4
        x = places[slot]
        y = places[slot + 1]
        life = places[slot + 2] - 1
        whole = places[slot + 3]
        if life <= 0:
            state = state * 69069 + 1
            x = (state >> 9) & 32767
            state = state * 69069 + 1
            y = (state >> 9) & 32767
            state = state * 69069 + 1
            life = 90 + ((state >> 16) & 255)
            whole = life
        places[slot + 2] = life
        places[slot + 3] = whole

        # the field here, blended between the four cells round it. their
        # middles are 8 px apart, 2048 in 256ths
        grid_x = (x - 1024) & 32767
        grid_y = (y - 1024) & 32767
        cell_x = grid_x >> 11
        cell_y = grid_y >> 11
        blend_x = (grid_x >> 3) & 255
        blend_y = (grid_y >> 3) & 255
        top_left = (cell_y & 15) * 16 + (cell_x & 15)
        top_right = (cell_y & 15) * 16 + ((cell_x + 1) & 15)
        bottom_left = ((cell_y + 1) & 15) * 16 + (cell_x & 15)
        bottom_right = ((cell_y + 1) & 15) * 16 + ((cell_x + 1) & 15)
        top = field_x[top_left] * 256 + (field_x[top_right] - field_x[top_left]) * blend_x
        bottom = field_x[bottom_left] * 256 + (field_x[bottom_right] - field_x[bottom_left]) * blend_x
        move_x = (top * 256 + (bottom - top) * blend_y) >> 16
        top = field_y[top_left] * 256 + (field_y[top_right] - field_y[top_left]) * blend_x
        bottom = field_y[bottom_left] * 256 + (field_y[bottom_right] - field_y[bottom_left]) * blend_x
        move_y = (top * 256 + (bottom - top) * blend_y) >> 16
        move_x = (move_x * pace) >> 8
        move_y = (move_y * pace) >> 8

        # its colour by how quick it is
        speed = (move_x if move_x >= 0 else -move_x) + (move_y if move_y >= 0 else -move_y)
        quickness = (speed * 256) // (quick + 1)
        quickness = quickness if quickness < 256 else 256
        shade = (mote * 37) % shades
        slow = inks[shade * 2]
        fast = inks[shade * 2 + 1]
        red = (slow & 255) + ((((fast & 255) - (slow & 255)) * quickness) >> 8)
        green = ((slow >> 8) & 255) + (((((fast >> 8) & 255) - ((slow >> 8) & 255)) * quickness) >> 8)
        blue = ((slow >> 16) & 255) + (((((fast >> 16) & 255) - ((slow >> 16) & 255)) * quickness) >> 8)

        # swelling in and tapering off
        age = whole - life
        swell = age if age < life else life
        swell = (swell * 256) // ramp
        swell = swell if swell < 256 else 256
        stroke_radius = 64 + (((radius - 64) * swell) >> 8)
        strength = (solid * swell) >> 8
        # squared radii in 256ths. out to where the edge fades away, in to where it's solid
        outer = ((stroke_radius + 128) * (stroke_radius + 128)) >> 8
        inner = ((stroke_radius - 128) * (stroke_radius - 128)) >> 8 if stroke_radius > 128 else 0
        span = (stroke_radius + 383) >> 8

        half = 0
        while half < 2:
            x = (x + (move_x >> 1)) & 32767
            y = (y + (move_y >> 1)) & 32767
            pixel_x = x >> 8
            pixel_y = y >> 8
            offset_y = -span
            while offset_y <= span:
                distance_y = (offset_y << 8) + 128 - (y & 255)
                offset_x = -span
                while offset_x <= span:
                    distance_x = (offset_x << 8) + 128 - (x & 255)
                    distance = (distance_x * distance_x + distance_y * distance_y) >> 8
                    if distance < outer:
                        cover = 256 if distance <= inner else ((outer - distance) * 256) // (outer - inner)
                        weight = (cover * strength) >> 8
                        i = ((pixel_y + offset_y) & 127) * 128 + ((pixel_x + offset_x) & 127)
                        under = pixels[i]
                        under_red = under & 255
                        under_green = (under >> 8) & 255
                        under_blue = (under >> 16) & 255
                        under_red += ((red - under_red) * weight) >> 8
                        under_green += ((green - under_green) * weight) >> 8
                        under_blue += ((blue - under_blue) * weight) >> 8
                        pixels[i] = OPAQUE | (under_blue << 16) | (under_green << 8) | under_red
                    offset_x += 1
                offset_y += 1
            half += 1
        places[slot] = x
        places[slot + 1] = y
        mote += 1
    seed[0] = state


# an (r, g, b) as a viper pixel, each clamped to a byte
def pack(rgb):
    red, green, blue = (max(0, min(255, int(channel))) for channel in rgb)
    return 0xFF000000 | blue << 16 | green << 8 | red


# from colour start toward colour end, amount 0 to 1
def mix(start, end, amount):
    return tuple(from_channel + (to_channel - from_channel) * amount for from_channel, to_channel in zip(start, end))


# the colour at heat on the WARMTH scale
def warmth(heat):
    if heat <= WARMTH[0][0]:
        return WARMTH[0][1]
    for (low, low_colour), (high, high_colour) in zip(WARMTH, WARMTH[1:]):
        if heat <= high:
            return mix(low_colour, high_colour, (heat - low) / (high - low))
    return WARMTH[-1][1]


# the stream and the one it's easing toward. their scale doesn't matter since
# flow_field() brings the wind to the mood's speed. SMOOTHING is room for smooth()
STREAM = array("i", bytes(4 * FIELD * FIELD))
GOAL = array("i", bytes(4 * FIELD * FIELD))
SMOOTHING = array("i", bytes(4 * FIELD * FIELD))


# makes each of the 16 x 16 values the average of itself and its eight
# neighbours, wrapping round the edges. room holds the results till the end
@micropython.viper
def smooth(values: ptr32, room: ptr32):
    i = 0
    while i < 256:
        cell_x = i & 15
        cell_y = i >> 4
        total = 0
        offset_y = -1
        while offset_y <= 1:
            row = ((cell_y + offset_y) & 15) * 16
            total += values[row + ((cell_x - 1) & 15)] + values[row + cell_x] + values[row + ((cell_x + 1) & 15)]
            offset_y += 1
        room[i] = total // 9
        i += 1
    i = 0
    while i < 256:
        values[i] = room[i]
        i += 1


# a random stream, smoothed so its highs and lows are broad
def new_stream():
    for i in range(FIELD * FIELD):
        GOAL[i] = int((random() * 2 - 1) * 65536)
    for _ in range(SMOOTHS):
        smooth(GOAL, SMOOTHING)


# works out the 16 x 16 wind field. first the stream eases ease 256ths toward
# its goal.
#
# the wind runs along the stream's slopes, round its highs and lows, never
# toward or away from one place. it's scaled to average speed 256ths of a px a
# frame, then the gentle wind_x, wind_y is added
@micropython.viper
def flow_field(stream: ptr32, goal: ptr32, field_x: ptr32, field_y: ptr32,
               ease: int, wind_x: int, wind_y: int, speed: int):
    i = 0
    while i < 256:
        stream[i] += ((goal[i] - stream[i]) * ease) >> 8
        i += 1
    total = 0
    i = 0
    while i < 256:
        cell_x = i & 15
        cell_y = i >> 4
        across = stream[((cell_y + 1) & 15) * 16 + cell_x] - stream[((cell_y - 1) & 15) * 16 + cell_x]
        down = stream[cell_y * 16 + ((cell_x - 1) & 15)] - stream[cell_y * 16 + ((cell_x + 1) & 15)]
        field_x[i] = across
        field_y[i] = down
        total += (across if across >= 0 else -across) + (down if down >= 0 else -down)
        i += 1
    # what brings the average to speed, in 4096ths
    scale = (speed * 256 * 4096) // (total + 1)
    i = 0
    while i < 256:
        field_x[i] = ((field_x[i] * scale) >> 12) + wind_x
        field_y[i] = ((field_y[i] * scale) >> 12) + wind_y
        i += 1


# the wind field for seconds in, elapsed seconds since it was last stirred
def stir(seconds, elapsed):
    heading = 2 * math.pi * seconds / VEER
    ease = int(min(1, EASE * elapsed) * 256)
    wind_x = int(math.sin(heading) * PREVAILING * 256)
    wind_y = int(-math.cos(heading) * PREVAILING * 256)
    flow_field(STREAM, GOAL, FIELD_X, FIELD_Y, ease, wind_x, wind_y, int(SWIRL_SPEED * 256))


# sets the inks for the given shades. from the scheme, or from where the
# colours have wandered to by seconds in
def colour(seconds, shades):
    swing = (1 - math.cos(2 * math.pi * seconds / WANDER)) / 2
    heat = WARMTH[0][0] + (WARMTH[-1][0] - WARMTH[0][0]) * swing
    for (_, _, _, _, bright), inks in zip(LAYERS, LAYER_INKS):
        for shade in shades:
            if SCHEME:
                # a scheme has fewer colours than SHADES
                if shade >= len(SCHEME):
                    continue
                base = SCHEME[shade]
            else:
                base = warmth(heat + (shade - SHADES // 2) * 0.6)
            inks[shade * 2] = pack(channel * bright for channel in mix(base, SLOW[0], SLOW[1]))
            inks[shade * 2 + 1] = pack(channel * bright for channel in mix(base, FAST[0], FAST[1]))


for y in range(128):
    SKY[y] = pack(mix(SKY_TOP, SKY_BOTTOM, (y / 127) ** 1.4))
canvas.pen = color.rgb(*SKY_TOP)
canvas.clear()
# motes start scattered by a fixed hash, partway through staggered lives so
# they don't all start again at once
for layer, places in zip(LAYERS, LAYER_PLACES):
    for mote in range(layer[0]):
        places[mote * 4] = (mote * 7919 + 13) * 97 % 32768
        places[mote * 4 + 1] = (mote * 104729 + 7) * 31 % 32768
        places[mote * 4 + 2] = 1 + mote * 53 % 255
        places[mote * 4 + 3] = 345
new_stream()
STREAM[:] = GOAL
colour(0, range(SHADES))
frame = 0
started = time.ticks_ms()
changed = started
stirred = started


def update():
    global frame, changed, stirred
    now = time.ticks_ms()
    seconds = time.ticks_diff(now, started) / 1000
    if time.ticks_diff(now, changed) >= STREAM_SECONDS * 1000:
        changed = now
        new_stream()
    if frame % FIELD_EVERY == 0:
        stir(seconds, time.ticks_diff(now, stirred) / 1000)
        stirred = now
    # one shade's inks a frame, so none takes long
    colour(seconds, (frame % SHADES,))
    frame += 1

    fade(CANVAS, SKY, TRAIL_KEEP)
    # the wind surging now and then
    surge = 1 + GUSTS * max(0, math.sin(seconds * 0.53) * math.sin(seconds * 0.19)) ** 2
    for (count, pace, width, solid, _), places, inks, style in zip(LAYERS, LAYER_PLACES, LAYER_INKS, LAYER_STYLES):
        style[0] = int(pace * surge * 256)
        # the radius, half the width in 256ths
        style[1] = int(width * 128)
        style[2] = solid
        style[3] = int(SWIRL_SPEED * 256 * pace * 1.3)
        style[4] = TAPER
        style[5] = len(SCHEME) if SCHEME else SHADES
        brush(CANVAS, places, count, FIELD_X, FIELD_Y, inks, SEED, style)
    screen.blit(canvas, 0, 0)
