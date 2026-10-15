import time
import micropython
from array import array
from micropython import const
from math import exp, sqrt

from plugin_config import plugin_config

# wall, haze, line glow, line colour down the corridor. ring glow and colour. hot core, far fade
SCHEMES = {
    "neon": ((0, 12, 28), (0, 30, 60), (0, 70, 140), (0, 220, 255), (110, 0, 90), (255, 60, 200), (230, 250, 255), (0, 0, 0)),
    "plaid": ((8, 6, 34), (24, 10, 50), (190, 60, 0), (255, 150, 30), (110, 0, 10), (235, 40, 25), (255, 240, 200), (0, 0, 0)),
    "emerald": ((0, 14, 8), (0, 34, 20), (60, 120, 0), (170, 255, 40), (0, 80, 50), (0, 210, 120), (230, 255, 220), (0, 0, 0)),
    "magenta": ((0, 12, 28), (0, 30, 60), (110, 0, 90), (255, 60, 200), (0, 70, 140), (0, 220, 255), (255, 225, 250), (0, 0, 0)),
    "blueprint": ((14, 52, 130), (24, 70, 150), (70, 120, 210), (235, 245, 255), (50, 100, 190), (140, 200, 255), (255, 255, 255), (12, 44, 112)),
}

cfg = plugin_config("neon_corridor", {
    "scheme": "neon",  # one of SCHEMES
    "speed": 70,  # 55 slow, 70 normal, 90 fast
})
scheme = cfg["scheme"]
speed = cfg["speed"]

# unknown names fall back to neon so the config page ticks what's showing
if scheme not in SCHEMES:
    scheme = "neon"
WALL, HAZE, GLOW_ALONG, LINE_ALONG, GLOW_RING, LINE_RING, CORE, FAR = SCHEMES[scheme]

# narrower view, bigger far end. any lower and ring width outgrows its 6 bits
ZOOM = 2
UNIT = 128  # depth steps in half the corridor's width
# depth steps between rings. a quarter of the width gives square cells (see bake())
RING = const(64)

# full fog where rings bunch under 1.5 px apart, starting a third of the way in
FOG_FAR = sqrt(64 * ZOOM * RING / UNIT / 1.5)
FOG_NEAR = FOG_FAR * 1.5 / 4.6

# palette sections
RING_COLOURS = const(1024)
GLOW = const(2048)
LIGHT = const(2112)


def mix(a, b, f):
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f)


# palette: lines then rings (16 fog rows x 64 strengths each), line glow, 16 light levels
PALETTE = array("I", [0] * 2128)
for block, (glow, line) in enumerate(((GLOW_ALONG, LINE_ALONG), (GLOW_RING, LINE_RING))):
    for f in range(16):
        near = 1 - f / 15
        wall = mix(FAR, WALL, near ** 1.6)
        wall = mix(wall, HAZE, 2 * near * (1 - near) * near)
        wall = (int(wall[0] + 0.5), int(wall[1] + 0.5), int(wall[2] + 0.5))
        for s in range(64):
            # wall -> glow -> line -> hot core, out of 3780
            a = 4 * s * (15 - f)
            if a < 1890:
                lo = wall
                hi = glow
                k = a
                span = 1890
            elif a < 3213:
                lo = glow
                hi = line
                k = a - 1890
                span = 1323
            else:
                lo = line
                hi = CORE
                k = a - 3213
                span = 567
            r = lo[0] + (hi[0] - lo[0]) * k // span
            g = lo[1] + (hi[1] - lo[1]) * k // span
            b = lo[2] + (hi[2] - lo[2]) * k // span
            PALETTE[block * RING_COLOURS + (f << 6) + s] = 0xff000000 | (b << 16) | (g << 8) | r

# a line is a 1 px core with a soft glow
for k in range(64):
    px = k / 4
    core = max(0, 1 - max(0, px - 0.25))
    PALETTE[GLOW + k] = int(63 * min(1, core + 0.45 * exp(-px / 1.6)) + 0.5)

# light gets added on top, line colour when faint up to the hot core
for k in range(16):
    c = mix(LINE_ALONG, CORE, k / 15)
    PALETTE[LIGHT + k] = (int(c[2] * k / 15) << 16) | (int(c[1] * k / 15) << 8) | int(c[0] * k / 15)

# depth | ring width | fog, all just from distance to the centre
OUT = []
for k in range(64):
    m = k + 0.5
    z = 64 * ZOOM / m
    depth = min(4095, int(z * UNIT + 0.5))
    # px per depth step, keeps rings the same width at any distance
    width = min(63, int(m * m / (32 * ZOOM) + 0.5))
    fog = max(0, min(15, int(15 * (z - FOG_NEAR) / (FOG_FAR - FOG_NEAR) + 0.5)))
    OUT.append(depth | (width << 12) | (fog << 24))

# light's hot dot + halo, then a ray, by distance in quarter px. quarter levels, 60 is full
GLARE = [int(60 * (exp(-k / 10) + 0.55 * exp(-k / 56))) for k in range(362)]
RAY = [48 * exp(-k / 88) for k in range(362)]

# one word a pixel, low to high: depth 12 bits | ring width 6 | line 6 | fog 4 | light 4.
# corners match, so one quarter gets copied. light's dithered 2x2.
# a function so names are fast locals
def bake():
    table = array("I", [0] * 128 * 128)
    dither = (0, 2, 3, 1)
    for qy in range(64):
        for qx in range(64):
            if qx > qy:
                far = qx
                side = qy
            else:
                far = qy
                side = qx
            # bigger and smaller of across/down, half px from the centre
            m2 = 2 * far + 1
            o2 = 2 * side + 1

            # quarter px to the nearest line: middle, halfway or corner
            across = 2 * o2
            if abs(2 * o2 - m2) < across:
                across = abs(2 * o2 - m2)
            if 2 * (m2 - o2) < across:
                across = 2 * (m2 - o2)
            if across > 63:
                across = 63
            word = OUT[far] | (PALETTE[GLOW + across] << 18)

            # hot dot, halo, and rays along the axes and diagonals
            r4 = int(2 * sqrt(o2 * o2 + m2 * m2))
            level = GLARE[r4]
            if side == 0 or far - side < 2:
                rays = max(0, 1 - (side + 0.5) / 1.2) + max(0, 1 - (far - side) * 0.7071 / 1.2)
                level += int(RAY[r4] * rays)
            if level > 60:
                level = 60

            y0 = (64 + qy) * 128
            y1 = (63 - qy) * 128
            x0 = 64 + qx
            x1 = 63 - qx
            a = qx & 1
            b = (qy & 1) * 2
            table[y0 + x0] = word | (((level + dither[b + a]) >> 2) << 28)
            table[y0 + x1] = word | (((level + dither[b + 1 - a]) >> 2) << 28)
            table[y1 + x0] = word | (((level + dither[2 - b + a]) >> 2) << 28)
            table[y1 + x1] = word | (((level + dither[3 - b - a]) >> 2) << 28)
    return table


TABLE = bake()

@micropython.viper
def corridor(table: ptr32, pixels: ptr32, pal: ptr32, travelled: int):  # noqa: F821
    i = 0
    while i < 16384:
        packed = table[i]

        # distance to the nearest ring
        to_ring = (packed + travelled) & (RING - 1)
        if to_ring > RING >> 1:
            to_ring = RING - to_ring
        ring_glow = (to_ring * ((packed >> 12) & 63)) >> 6
        if ring_glow > 63:
            ring_glow = 63
        ring = int(pal[GLOW + ring_glow])

        along = (packed >> 18) & 63
        colour_step = along + ring
        if colour_step > 63:
            colour_step = 63
        if ring > along:
            colour_step += RING_COLOURS
        colour = int(pal[((packed >> 18) & 0x3c0) + colour_step])

        light_level = (packed >> 28) & 15
        if light_level:
            light = int(pal[LIGHT + light_level])
            red = (colour & 255) + (light & 255)
            if red > 255:
                red = 255
            green = ((colour >> 8) & 255) + ((light >> 8) & 255)
            if green > 255:
                green = 255
            blue = ((colour >> 16) & 255) + ((light >> 16) & 255)
            if blue > 255:
                blue = 255
            colour = ((colour >> 24) << 24) | (blue << 16) | (green << 8) | red

        pixels[i] = colour
        i += 1


# depth steps travelled, in thousandths, wraps at one ring
travelled = 0
last = time.ticks_ms()


def update():
    global travelled, last

    t = time.ticks_ms()
    travelled = (travelled + time.ticks_diff(t, last) * speed) % (RING * 1000)
    last = t

    corridor(TABLE, memoryview(screen), PALETTE, travelled // 1000)
