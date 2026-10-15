import time
import micropython
from array import array
from random import randrange

from plugin_config import plugin_config

# shadow side, calm water, lit side
SCHEMES = {
    "deep_sea": [(0, 4, 14), (4, 22, 52), (70, 150, 170)],
    "pond": [(2, 8, 4), (10, 34, 20), (120, 170, 110)],
    "moonlit": [(0, 0, 2), (8, 10, 18), (170, 175, 190)],
    "lagoon": [(0, 14, 18), (6, 60, 70), (110, 210, 200)],
    "sunset": [(8, 2, 14), (40, 12, 40), (230, 150, 50)],
}

cfg = plugin_config("ripples", {
    "scheme": "deep_sea",  # one of SCHEMES
    "rain": 2,  # 1 light, 2 steady, 4 heavy
})
scheme = cfg["scheme"]
rain = cfg["rain"]

STOPS = SCHEMES.get(scheme, SCHEMES["deep_sea"])

# calm water sits at 128
PALETTE = array("I", [0] * 256)
for i in range(256):
    if i < 128:
        lo = STOPS[0]
        hi = STOPS[1]
        f = i / 128
    else:
        lo = STOPS[1]
        hi = STOPS[2]
        f = (i - 128) / 127
    r = int(lo[0] + (hi[0] - lo[0]) * f)
    g = int(lo[1] + (hi[1] - lo[1]) * f)
    b = int(lo[2] + (hi[2] - lo[2]) * f)
    PALETTE[i] = 0xff000000 | (b << 16) | (g << 8) | r

# water height now and a frame ago. edges stay 0 so waves bounce
now = array("i", [0] * 128 * 128)
before = array("i", [0] * 128 * 128)

DROP = 2048  # how hard a raindrop pushes the water
next_drop = time.ticks_ms()

# soft round drops, hard ones leave a pitted look. (offset, height) pairs
DROP_SHAPE = []
for dy in range(-4, 5):
    for dx in range(-4, 5):
        d2 = dx * dx + dy * dy
        if d2 < 16:
            k = 1 - d2 / 16
            DROP_SHAPE.append((dy * 128 + dx, int(DROP * k * k)))


# steps the water into before and lights it from now. light is the slope
@micropython.viper
def ripple(now: ptr32, before: ptr32, pixels: ptr32, pal: ptr32):  # noqa: F821
    row = 128
    while row < 16256:
        i = row + 1
        end = row + 127
        while i < end:
            left = int(now[i - 1])
            right = int(now[i + 1])
            up = int(now[i - 128])
            down = int(now[i + 128])

            # half the neighbours minus where it was, shrunk so waves die out
            next_height = ((left + right + up + down) >> 1) - int(before[i])
            before[i] = next_height - (next_height >> 4)

            light = ((right - left + down - up) >> 4) + 128
            if light < 0:
                light = 0
            elif light > 255:
                light = 255
            pixels[i] = pal[light]
            i += 1
        row += 128

    # edge never moves, so it's always flat water
    calm = pal[128]
    i = 0
    while i < 128:
        pixels[i] = calm
        pixels[16256 + i] = calm
        pixels[i << 7] = calm
        pixels[(i << 7) + 127] = calm
        i += 1


def update():
    global now, before, next_drop

    t = time.ticks_ms()

    if time.ticks_diff(t, next_drop) >= 0:
        centre = randrange(6, 122) * 128 + randrange(6, 122)
        for offset, height in DROP_SHAPE:
            now[centre + offset] += height
        # steady is a drop every 0.25-0.7 s
        next_drop = time.ticks_add(t, randrange(500, 1400) // rain)

    ripple(now, before, memoryview(screen), PALETTE)
    now, before = before, now
