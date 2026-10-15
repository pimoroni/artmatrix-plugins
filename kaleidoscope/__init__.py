import math
import time
import micropython
from array import array
from random import choice

from plugin_config import plugin_config

# lead, up glass, down glass
SCHEMES = {
    "sand": [(0, 0, 0), (230, 160, 40), (20, 90, 150)],
    "neon": [(0, 0, 4), (40, 210, 220), (210, 40, 170)],
    "ember": [(0, 0, 0), (240, 120, 20), (170, 10, 30)],
    "ice": [(0, 0, 4), (150, 200, 240), (90, 60, 190)],
    "mono": [(0, 0, 0), (200, 200, 200), (80, 80, 90)],
}

# (n, m, sign): humps per wave, sign 1 adds the second wave, -1 takes it away
SIMPLE = [(1, 2, -1), (1, 3, 1), (2, 3, -1), (1, 4, 1), (2, 5, -1), (1, 5, -1), (3, 4, 1)]
BUSY = SIMPLE + [(3, 5, 1), (2, 7, -1), (4, 7, 1), (3, 8, -1), (5, 6, 1), (1, 8, 1)]

# ms a figure stays still, then ms to melt into the next
PACES = {1: (8000, 4000), 2: (4500, 2500), 3: (2500, 1500)}

cfg = plugin_config("kaleidoscope", {
    "scheme": "sand",  # one of SCHEMES
    "pace": 2,  # 1 slow, 2 medium, 3 fast
    "detail": "simple",  # simple or busy
})
scheme = cfg["scheme"]
pace = cfg["pace"]
detail = cfg["detail"]

STOPS = SCHEMES.get(scheme, SCHEMES["sand"])
FIGURES = BUSY if detail == "busy" else SIMPLE
HOLD, FADE = PACES.get(pace, PACES[2])

# down glass then up glass, 256 each, 0 = still line. lead goes to glass fast, panes glow
PALETTE = array("I", [0] * 512)
for start, glass in ((0, STOPS[2]), (256, STOPS[1])):
    for i in range(256):
        if i < 64:
            lo = STOPS[0]
            hi = glass
            f = i / 64
        else:
            lo = glass
            hi = (255, 255, 255)
            f = (i - 64) / 191 * 0.3
        r = int(lo[0] + (hi[0] - lo[0]) * f)
        g = int(lo[1] + (hi[1] - lo[1]) * f)
        b = int(lo[2] + (hi[2] - lo[2]) * f)
        PALETTE[start + i] = 0xff000000 | (b << 16) | (g << 8) | r

# two figures, 512 each: wave 1 across, wave 2 across, then both down. x256
TABLES = array("i", [0] * 1024)

# weights (0-256), then where each figure starts in TABLES
PARAMS = array("i", [256, 0, 0, 512])


def bake(start, figure):
    n, m, sign = figure
    for i in range(128):
        u = (i - 63.5) / 63.5 * math.pi
        a = int(math.cos(n * u) * 256)
        b = int(math.cos(m * u) * 256)
        TABLES[start + i] = a
        TABLES[start + 128 + i] = b * sign
        TABLES[start + 256 + i] = b
        TABLES[start + 384 + i] = a


# height is across x down +/- swapped, 0 = still. direction picks glass, distance brightness
@micropython.viper
def plate(tables: ptr32, settings: ptr32, pixels: ptr32, pal: ptr32):  # noqa: F821
    weight_now = int(settings[0])
    weight_next = int(settings[1])
    now_at = int(settings[2])
    next_at = int(settings[3])
    i = 0
    y = 0
    while y < 128:
        now_down1 = int(tables[now_at + 256 + y])
        now_down2 = int(tables[now_at + 384 + y])
        next_down1 = int(tables[next_at + 256 + y])
        next_down2 = int(tables[next_at + 384 + y])
        x = 0
        while x < 128:
            height = (int(tables[now_at + x]) * now_down1 + int(tables[now_at + 128 + x]) * now_down2) * weight_now
            # only while melting into the next figure
            if weight_next:
                height += (int(tables[next_at + x]) * next_down1 + int(tables[next_at + 128 + x]) * next_down2) * weight_next
            glass = 256
            if height < 0:
                height = -height
                glass = 0
            height >>= 16
            if height > 255:
                height = 255
            pixels[i] = pal[glass + height]
            i += 1
            x += 1
        y += 1


figure = choice(FIGURES)
bake(0, figure)
following = choice([f for f in FIGURES if f != figure])
bake(512, following)
start = time.ticks_ms()


def update():
    global figure, following, start

    t = time.ticks_ms()
    elapsed = time.ticks_diff(t, start)

    if elapsed >= HOLD + FADE:
        # next figure's arrived, swap slots and refill the old one
        PARAMS[2], PARAMS[3] = PARAMS[3], PARAMS[2]
        figure = following
        following = choice([f for f in FIGURES if f != figure])
        bake(PARAMS[3], following)
        start = t
        elapsed = 0

    fade = 0
    if elapsed > HOLD:
        f = (elapsed - HOLD) / FADE
        fade = int(f * f * (3 - 2 * f) * 256)

    # breathe between 75% and 100% every ~2 s
    ring = 224 + int(32 * math.cos(t * 0.00314))
    PARAMS[0] = ((256 - fade) * ring) >> 8
    PARAMS[1] = (fade * ring) >> 8

    plate(TABLES, PARAMS, memoryview(screen), PALETTE)
