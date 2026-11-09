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

# unknown values fall back to the defaults so the config page ticks what's
# showing
if scheme not in SCHEMES:
    scheme = "deep_sea"
if rain not in (1, 2, 4):
    rain = 2

DEEP, SKY, GLINT = SCHEMES[scheme]

# water height is 16 bits a cell, offset so calm water is LEVEL. a cell's
# height now and a step ago sit side by side, so one PSRAM read gets both.
# the edges stay calm, so waves bounce off them
LEVEL = const(32768)
WATER = array("H", [LEVEL] * 128 * 128 * 2)

# the frames take turns over which of each pair is now. these views start
# on the first and second of each pair, so a cell is at [i * 2] in both
HALVES = (memoryview(WATER), memoryview(WATER)[1:])
now_half = 0

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

# lighting for every slope across and down, 64 x 64, flat water in the middle
TABLE = 64
TABLE_MIDDLE = const(32)
TABLE_EDGE = const(63)
TABLE_ROW_SHIFT = const(6)
STEEPEST = 1.0
# the sun is low, so only the steepest faces catch its glint. the glint is
# tight
SUN_FROM = (-0.6, -0.7, 0.3)
SHINE = 400
REFLECT = 0.05

# how much the water is lifted above its scheme colours, glints aside
LIFT = 1.8


def pack(red, green, blue):
    return 0xff000000 | (int(blue) << 16) | (int(green) << 8) | int(red)


def sunlit():
    lit = array("I", [0] * TABLE * TABLE)
    sun_x, sun_y, sun_z = SUN_FROM
    size = math.sqrt(sun_x * sun_x + sun_y * sun_y + sun_z * sun_z)
    sun_x, sun_y, sun_z = sun_x / size, sun_y / size, sun_z / size
    # the glint peaks where the water faces halfway between the sun and the
    # viewer straight above
    halfway_x, halfway_y, halfway_z = sun_x, sun_y, sun_z + 1
    size = math.sqrt(halfway_x * halfway_x + halfway_y * halfway_y + halfway_z * halfway_z)
    halfway_x, halfway_y, halfway_z = halfway_x / size, halfway_y / size, halfway_z / size
    half = TABLE // 2
    for row in range(TABLE):
        slope_y = (row - half) / half * STEEPEST
        for column in range(TABLE):
            slope_x = (column - half) / half * STEEPEST
            size = math.sqrt(slope_x * slope_x + slope_y * slope_y + 1)
            normal_x, normal_y, normal_z = -slope_x / size, -slope_y / size, 1 / size
            facing = max(0.0, normal_x * sun_x + normal_y * sun_y + normal_z * sun_z)
            glint = max(0.0, normal_x * halfway_x + normal_y * halfway_y + normal_z * halfway_z) ** SHINE
            reflect = REFLECT + (1 - REFLECT) * (1 - normal_z) ** 5
            shade = (0.3 + 1.1 * facing) * (1 - reflect)
            lit[row * TABLE + column] = pack(*[min(255, (DEEP[channel] * shade + SKY[channel] * reflect) * LIFT + GLINT[channel] * glint) for channel in range(3)])
    return lit


LIT = sunlit()

# how many height units of slope reach the edge of the lighting table
SLOPE_SHIFT = const(5)

# under the ripples a gentle swell moves the whole surface: (wavelength px,
# heading degrees, steepness in lighting table steps)
SWELLS = [(74, 20, 11), (41, -55, 8)]

# a swell's phase is in 1/256 turn, with 16 bits of fraction below that
PHASE_FRACTION = const(16)
TURN = 256 << PHASE_FRACTION

# each swell's slope at every 1/256 turn: across in the top 16 bits and down
# in the bottom 16, both x16
SWELL_SLOPES = array("i", [0] * 2 * 256)

# per swell: its phase at the top left pixel, then how far that moves for
# each column across and each row down
SWELL_PHASES = array("i", [0] * 2 * 3)

# how far each swell's phase moves per ms as it travels
SWELL_SPEEDS = []

for swell, (wavelength, heading, steepness) in enumerate(SWELLS):
    heading_x = math.cos(math.radians(heading))
    heading_y = math.sin(math.radians(heading))
    SWELL_PHASES[swell * 3 + 1] = int(TURN * heading_x / wavelength)
    SWELL_PHASES[swell * 3 + 2] = int(TURN * heading_y / wavelength)
    radians_per_second = math.sqrt(9 * 2 * math.pi / wavelength)
    SWELL_SPEEDS.append(int(TURN * radians_per_second / (2 * math.pi) / 1000))
    for step in range(256):
        rise = math.sin(step * 2 * math.pi / 256)
        across = round(steepness * heading_x * rise * 16)
        down = round(steepness * heading_y * rise * 16)
        SWELL_SLOPES[swell * 256 + step] = (across << 16) | (down & 0xFFFF)


# one step of the wave: each cell moves toward the average of its eight
# neighbours and past it by how far it was moving, losing a little each time.
# then each pixel is lit by its slope across and down
@micropython.viper
def ripple(now: ptr16, before: ptr16, pixels: ptr32, lit: ptr32,  # noqa: F821
           swell_slopes: ptr32, swell_phases: ptr32):  # noqa: F821
    first_phase = int(swell_phases[0])
    first_per_column = int(swell_phases[1])
    first_per_row = int(swell_phases[2])
    second_phase = int(swell_phases[3])
    second_per_column = int(swell_phases[4])
    second_per_row = int(swell_phases[5])

    y = 1
    while y < 127:
        # each swell's phase at the first pixel of the row
        first = first_phase + first_per_row * y + first_per_column
        second = second_phase + second_per_row * y + second_per_column

        # a cell's heights are at [i * 2], so the rows above and below are 256
        # away. the 3 x 3 of heights around the pixel is kept less LEVEL, and
        # stepping along a pixel only reads the new column on the right
        i = (y << 7) + 1
        at = i << 1
        up_left = int(now[at - 258]) - LEVEL
        up = int(now[at - 256]) - LEVEL
        left = int(now[at - 2]) - LEVEL
        middle = int(now[at]) - LEVEL
        down_left = int(now[at + 254]) - LEVEL
        down = int(now[at + 256]) - LEVEL
        end = i + 126
        while i < end:
            up_right = int(now[at - 254]) - LEVEL
            right = int(now[at + 2]) - LEVEL
            down_right = int(now[at + 258]) - LEVEL

            # sides count twice the corners, so rings spread round, not square
            sides = left + right + up + down
            corners = up_left + up_right + down_left + down_right
            next_height = ((sides * 2 + corners) * 170 >> 10) - (int(before[at]) - LEVEL)
            next_height -= next_height >> LOSS
            if next_height > 32000:
                next_height = 32000
            elif next_height < -32000:
                next_height = -32000
            before[at] = next_height + LEVEL

            # the swell under it all, then the ripples on top. the bottom 16
            # bits of a swell slope are signed, so they're flipped about 0x8000
            first_slope = int(swell_slopes[(first >> PHASE_FRACTION) & 255])
            second_slope = int(swell_slopes[256 + ((second >> PHASE_FRACTION) & 255)])
            swell_across = (first_slope >> 16) + (second_slope >> 16)
            swell_down = ((first_slope & 0xFFFF) ^ 0x8000) + ((second_slope & 0xFFFF) ^ 0x8000) - 0x10000
            across = TABLE_MIDDLE + ((right - left) >> SLOPE_SHIFT) + (swell_across >> 4)
            along = TABLE_MIDDLE + ((down - up) >> SLOPE_SHIFT) + (swell_down >> 4)
            if across < 0:
                across = 0
            elif across > TABLE_EDGE:
                across = TABLE_EDGE
            if along < 0:
                along = 0
            elif along > TABLE_EDGE:
                along = TABLE_EDGE
            pixels[i] = lit[(along << TABLE_ROW_SHIFT) | across]

            up_left = up
            up = up_right
            left = middle
            middle = right
            down_left = down
            down = down_right
            first += first_per_column
            second += second_per_column
            i += 1
            at += 2
        y += 1

    # the edge cells never move, so each border pixel copies the one next to
    # it, which has the swell on it
    y = 1
    while y < 127:
        row = y << 7
        pixels[row] = pixels[row + 1]
        pixels[row + 127] = pixels[row + 126]
        y += 1
    x = 0
    while x < 128:
        pixels[x] = pixels[128 + x]
        pixels[16256 + x] = pixels[16128 + x]
        x += 1


# pushes a soft round drop into the water
@micropython.viper
def splash(now: ptr16, x: int, y: int, radius: int, height: int, profile: ptr32):  # noqa: F821
    radius_squared = radius * radius
    offset_y = -radius
    while offset_y <= radius:
        pixel_y = y + offset_y
        if 1 <= pixel_y < 127:
            offset_x = -radius
            while offset_x <= radius:
                pixel_x = x + offset_x
                distance_squared = offset_x * offset_x + offset_y * offset_y
                if 1 <= pixel_x < 127 and distance_squared < radius_squared:
                    push = int(profile[(distance_squared * 64) // radius_squared])
                    at = ((pixel_y << 7) | pixel_x) << 1
                    pushed = int(now[at]) + ((height * push) >> 8)
                    now[at] = 65535 if pushed > 65535 else (0 if pushed < 0 else pushed)
                offset_x += 1
        offset_y += 1


def drop(height, radius):
    splash(HALVES[now_half], 6 + getrandbits(7) % 116, 6 + getrandbits(7) % 116, radius, height, FINE if getrandbits(1) else BROAD)


def between(low, high):
    return low + getrandbits(16) * (high - low) // 65536


start = time.ticks_ms()
next_drop = start
next_big = time.ticks_add(start, BIG_EVERY * 1000)
last_frame = start


def update():
    global now_half, next_drop, next_big, last_frame

    ticks = time.ticks_ms()

    if time.ticks_diff(ticks, next_big) >= 0:
        drop(STONE, STONE_RADIUS)
        next_big = time.ticks_add(ticks, int(BIG_EVERY * 1000 * (0.6 + getrandbits(8) / 320)))

    if time.ticks_diff(ticks, next_drop) >= 0:
        drop(between(*DROP), between(*RADIUS))
        next_drop = time.ticks_add(ticks, int(between(*BETWEEN) / rain))

    # move each swell on by the time since the last frame. the phase wraps at
    # a turn, so it stays exact however long the plugin runs
    elapsed = time.ticks_diff(ticks, last_frame)
    last_frame = ticks
    for swell in range(2):
        SWELL_PHASES[swell * 3] = (SWELL_PHASES[swell * 3] - elapsed * SWELL_SPEEDS[swell]) % TURN

    after = 1 - now_half
    ripple(HALVES[now_half], HALVES[after], memoryview(screen), LIT, SWELL_SLOPES, SWELL_PHASES)
    now_half = after
