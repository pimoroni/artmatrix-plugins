import math
import time
import micropython
from array import array
from micropython import const
from random import getrandbits

from plugin_config import plugin_config

# deep water, the sky it reflects, and the light's glints
SCHEMES = {
    "deep_sea": [(2, 14, 36), (90, 150, 190), (240, 250, 255)],
    "pond": [(6, 22, 12), (110, 160, 120), (240, 255, 220)],
    "moonlit": [(2, 3, 10), (60, 70, 100), (225, 230, 250)],
    "lagoon": [(2, 40, 48), (120, 210, 200), (250, 255, 245)],
    "sunset": [(20, 6, 28), (210, 110, 90), (255, 220, 150)],
}

cfg = plugin_config("ripples", {
    "scheme": "deep_sea",  # one of SCHEMES
    "rain": 2,  # 1 light, 2 steady, 4 heavy
})
scheme = cfg["scheme"]
rain = cfg["rain"]

DEEP, SKY, GLINT = SCHEMES.get(scheme, SCHEMES["deep_sea"])

# water height is 16 bits a cell, offset so calm water is LEVEL: now and a
# step ago. the edges stay calm, so waves bounce back off them
LEVEL = const(32768)
NOW = array("H", [LEVEL] * 128 * 128)
BEFORE = array("H", [LEVEL] * 128 * 128)

# how much of each wave is lost every step, as a shift. 6 loses 1/64, so
# ripples run right across the pool and through each other
LOSS = const(6)

# drops: how hard they push, smallest to largest, their radius in px, and
# between drops in ms at steady rain
DROP = (1200, 4000)
RADIUS = (3, 7)
BETWEEN = (180, 600)

# a stone this big drops in now and then
STONE = 7000
STONE_RADIUS = 11

# this wave won't spread a drop into rings like real water, so each drop
# starts as a few: a bump in the middle, then troughs and crests to its edge.
# by distance from the middle squared, out of 64, x256
def rings(turns):
    return array("i", [int(256 * math.cos(math.sqrt(i / 64) * turns * math.pi) * (1 - math.sqrt(i / 64)) ** 1.5) for i in range(64)])


BROAD = rings(2.5)
FINE = rings(4.5)

# about how many seconds between stones
BIG_EVERY = 6

# lighting for every slope across and down, 64 x 64
TABLE = 64
STEEPEST = 1.0
# the sun is low, so only the steepest faces catch its glint. the glint is
# tight
SUN_FROM = (-0.6, -0.7, 0.3)
SHINE = 400
REFLECT = 0.05

# how much the water is lifted above its scheme colours, glints aside
LIFT = 1.8


def pack(r, g, b):
    return 0xff000000 | (int(b) << 16) | (int(g) << 8) | int(r)


def sunlit():
    lit = array("I", [0] * TABLE * TABLE)
    sx, sy, sz = SUN_FROM
    size = math.sqrt(sx * sx + sy * sy + sz * sz)
    sx, sy, sz = sx / size, sy / size, sz / size
    hx, hy, hz = sx, sy, sz + 1
    size = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / size, hy / size, hz / size
    half = TABLE // 2
    for row in range(TABLE):
        dy = (row - half) / half * STEEPEST
        for column in range(TABLE):
            dx = (column - half) / half * STEEPEST
            size = math.sqrt(dx * dx + dy * dy + 1)
            nx, ny, nz = -dx / size, -dy / size, 1 / size
            facing = max(0.0, nx * sx + ny * sy + nz * sz)
            glint = max(0.0, nx * hx + ny * hy + nz * hz) ** SHINE
            reflect = REFLECT + (1 - REFLECT) * (1 - nz) ** 5
            shade = (0.3 + 1.1 * facing) * (1 - reflect)
            lit[row * TABLE + column] = pack(*[min(255, (DEEP[c] * shade + SKY[c] * reflect) * LIFT + GLINT[c] * glint) for c in range(3)])
    return lit


LIT = sunlit()

# how many height units of slope reach the edge of the lighting table
SLOPE_SHIFT = const(5)

# under the ripples a gentle swell moves the whole surface: (wavelength px,
# heading degrees, steepness in lighting table steps)
SWELLS = [(74, 20, 11), (41, -55, 8)]

# swell slope is steepness times sin(x + y), x its phase across, y its phase
# down plus travel. that's sin(x) cos(y) + cos(x) sin(y). so per column,
# sin(x) then cos(x) x256. per row, what multiplies them each frame
SWELL_COLUMNS = array("i", [0] * 128 * 4)
SWELL_ROWS = array("i", [0] * 128 * 8)

# per swell: its phase down per row and travelled, in 1/1024 turn, then its
# steepness across and down, x256
SWELL_PARAMS = array("i", [0] * 8)
SWELL_DOWN = []
SWELL_SPEED = []
for _w, (_length, _heading, _steep) in enumerate(SWELLS):
    _k = 2 * math.pi / _length
    _kx = _k * math.cos(math.radians(_heading))
    _ky = _k * math.sin(math.radians(_heading))
    for _x in range(128):
        SWELL_COLUMNS[_x * 4 + _w * 2] = int(math.sin(_kx * _x) * 256)
        SWELL_COLUMNS[_x * 4 + _w * 2 + 1] = int(math.cos(_kx * _x) * 256)
    SWELL_DOWN.append(_ky * 1024 / (2 * math.pi))
    SWELL_SPEED.append(math.sqrt(9 * _k) * 1024 / (2 * math.pi))
    SWELL_PARAMS[_w * 4 + 2] = int(_steep * 256 * math.cos(math.radians(_heading)))
    SWELL_PARAMS[_w * 4 + 3] = int(_steep * 256 * math.sin(math.radians(_heading)))

SIN = array("i", [int(math.sin(i * 2 * math.pi / 1024) * 256) for i in range(1024)])


# fills SWELL_ROWS: for each row and swell, what multiplies the column's sin
# and cos for the slope across, then for the slope down
@micropython.viper
def swell_rows(rows: ptr32, params: ptr32, sin: ptr32, down: ptr32):  # noqa: F821
    y = 0
    while y < 128:
        w = 0
        while w < 2:
            b = (int(down[w * 128 + y]) + int(params[w * 4])) & 1023
            cb = int(sin[(b + 256) & 1023])
            sb = int(sin[b])
            across = int(params[w * 4 + 2])
            along = int(params[w * 4 + 3])
            o = y * 8 + w * 4
            rows[o] = (across * cb) >> 8
            rows[o + 1] = (across * sb) >> 8
            rows[o + 2] = (along * cb) >> 8
            rows[o + 3] = (along * sb) >> 8
            w += 1
        y += 1


# each swell's phase down each row, in 1/1024 turn
SWELL_ROW_PHASE = array("i", [0] * 2 * 128)
for _w in range(2):
    for _y in range(128):
        SWELL_ROW_PHASE[_w * 128 + _y] = int(SWELL_DOWN[_w] * _y)


# one step of the wave: each cell moves toward the average of its eight
# neighbours and past it by how far it was moving, losing a little each time.
# then each pixel is lit by its slope across and down
@micropython.viper
def ripple(now: ptr16, before: ptr16, pixels: ptr32, lit: ptr32,  # noqa: F821
           columns: ptr32, rows: ptr32):  # noqa: F821
    row = 128
    while row < 16256:
        y8 = (row >> 7) * 8
        ac1 = int(rows[y8])
        as1 = int(rows[y8 + 1])
        dc1 = int(rows[y8 + 2])
        ds1 = int(rows[y8 + 3])
        ac2 = int(rows[y8 + 4])
        as2 = int(rows[y8 + 5])
        dc2 = int(rows[y8 + 6])
        ds2 = int(rows[y8 + 7])
        i = row + 1
        end = row + 127
        while i < end:
            left = int(now[i - 1]) - LEVEL
            right = int(now[i + 1]) - LEVEL
            up = int(now[i - 128]) - LEVEL
            down = int(now[i + 128]) - LEVEL

            # sides count twice the corners, so rings spread round, not square
            corners = (int(now[i - 129]) + int(now[i - 127]) + int(now[i + 127]) + int(now[i + 129])) - 4 * LEVEL
            next_height = (((left + right + up + down) * 2 + corners) * 170 >> 10) - (int(before[i]) - LEVEL)
            next_height -= next_height >> LOSS
            if next_height > 32000:
                next_height = 32000
            elif next_height < -32000:
                next_height = -32000
            before[i] = next_height + LEVEL

            # the swell under it all, then the ripples on top
            c4 = (i & 127) * 4
            sa1 = int(columns[c4])
            ca1 = int(columns[c4 + 1])
            sa2 = int(columns[c4 + 2])
            ca2 = int(columns[c4 + 3])
            across = 32 + ((right - left) >> SLOPE_SHIFT) + ((sa1 * ac1 + ca1 * as1 + sa2 * ac2 + ca2 * as2) >> 16)
            along = 32 + ((down - up) >> SLOPE_SHIFT) + ((sa1 * dc1 + ca1 * ds1 + sa2 * dc2 + ca2 * ds2) >> 16)
            if across < 0:
                across = 0
            elif across > 63:
                across = 63
            if along < 0:
                along = 0
            elif along > 63:
                along = 63
            pixels[i] = lit[(along << 6) | across]
            i += 1
        row += 128

    # the edge never moves, so it's always calm water
    calm = lit[(32 << 6) | 32]
    i = 0
    while i < 128:
        pixels[i] = calm
        pixels[16256 + i] = calm
        pixels[i << 7] = calm
        pixels[(i << 7) + 127] = calm
        i += 1


# pushes a soft round drop into the water
@micropython.viper
def splash(now: ptr16, x: int, y: int, radius: int, height: int, profile: ptr32):  # noqa: F821
    r2 = radius * radius
    dy = -radius
    while dy <= radius:
        py = y + dy
        if 1 <= py < 127:
            dx = -radius
            while dx <= radius:
                px = x + dx
                d2 = dx * dx + dy * dy
                if 1 <= px < 127 and d2 < r2:
                    k = int(profile[(d2 * 64) // r2])
                    at = (py << 7) | px
                    v = int(now[at]) + ((height * k) >> 8)
                    now[at] = 65535 if v > 65535 else (0 if v < 0 else v)
                dx += 1
        dy += 1


def drop(height, radius):
    splash(NOW, 6 + getrandbits(7) % 116, 6 + getrandbits(7) % 116, radius, height, FINE if getrandbits(1) else BROAD)


def between(lo, hi):
    return lo + getrandbits(16) * (hi - lo) // 65536


start = time.ticks_ms()
next_drop = start
next_big = start + BIG_EVERY * 1000


def update():
    global NOW, BEFORE, next_drop, next_big

    t = time.ticks_ms()

    if time.ticks_diff(t, next_big) >= 0:
        drop(STONE, STONE_RADIUS)
        next_big = time.ticks_add(t, int(BIG_EVERY * 1000 * (0.6 + getrandbits(8) / 320)))

    if time.ticks_diff(t, next_drop) >= 0:
        drop(between(*DROP), between(*RADIUS))
        next_drop = time.ticks_add(t, int(between(*BETWEEN) / rain))

    seconds = time.ticks_diff(t, start) / 1000
    for w in range(2):
        SWELL_PARAMS[w * 4] = int(-seconds * SWELL_SPEED[w]) & 1023
    swell_rows(SWELL_ROWS, SWELL_PARAMS, SIN, SWELL_ROW_PHASE)

    ripple(NOW, BEFORE, memoryview(screen), LIT, SWELL_COLUMNS, SWELL_ROWS)
    NOW, BEFORE = BEFORE, NOW
