import math
import os
import time
import micropython
from array import array
from micropython import const
from binascii import crc32
from random import uniform

from plugin_config import plugin_config

# deep water, sky it reflects, sun glints
SCHEMES = {
    "ocean": [(2, 22, 44), (120, 175, 205), (255, 250, 235)],
    "lagoon": [(2, 44, 46), (140, 210, 200), (255, 255, 240)],
    "dusk": [(22, 8, 40), (225, 120, 120), (255, 220, 160)],
    "night": [(1, 3, 12), (50, 66, 100), (220, 228, 245)],
}

# (wavelength px, heading degrees, steepness): a long swell, then crossing
# seas and chop from all round
SEAS = {
    "calm": [(72, 0, 0.16), (48, 38, 0.13), (33, -52, 0.11), (23, 84, 0.09), (16, -18, 0.07), (11, 128, 0.05)],
    "breezy": [(64, 0, 0.22), (44, 41, 0.2), (31, -56, 0.18), (22, 88, 0.15), (15, -22, 0.12), (10, 133, 0.09)],
    "choppy": [(56, 0, 0.26), (38, 44, 0.25), (27, -60, 0.23), (19, 92, 0.2), (13, -26, 0.17), (9, 138, 0.13)],
}

cfg = plugin_config("ocean", {
    "scheme": "ocean",  # one of SCHEMES
    "sea": "breezy",  # one of SEAS
    "listen": 1,  # 1 to react to sound, 0 to ignore it
})
scheme = cfg["scheme"]
sea = cfg["sea"]
listen = cfg["listen"]

# unknown names fall back to the defaults so the config page ticks what's showing
if scheme not in SCHEMES:
    scheme = "ocean"
if sea not in SEAS:
    sea = "breezy"
DEEP, SKY, SUN = SCHEMES[scheme]
WAVES = SEAS[sea]
COUNT = len(WAVES)

# render() is written out for six waves on a 2 px grid. ROW_TERMS is their
# cos and sin multipliers for one grid row
assert COUNT == 6
ROW_TERMS = const(12)

hearing = mic if listen else None

# pulls wavelength into speed the way deep water does, longer is faster
GRAVITY = 30

# then each wave's speed is scaled again, so the layers slide past each other
# instead of their interference moving as one. negative ones run back against
# the rest
SPEED_SPREAD = (1.0, -0.5, 1.7, 0.7, -2.2, 1.3)

# each wave's height drifts between these shares of itself over its period in
# seconds, so the waves gather into sets and calm patches
GROUP_LOW = const(179)  # of 256
GROUP_PERIODS = (23, 17, 29, 13, 19, 11)

# sun from the upper left and fairly low, seen from straight above. its glint
# is a hard core of SHINE with a softer SHEEN around it
SUN_FROM = (-0.55, -0.6, 0.58)
SHINE = 160
SHEEN = 24
SHEEN_SHARE = 0.25

# how far the light falls from faces toward the sun to faces away
LIGHT_RANGE = (0.3, 1.3)

# slopes are exaggerated this much for the lighting, so small ripples show
BUMP = 1.7

# how much light the water gives back seen straight on, rising to all of it
# at a glance
REFLECT = 0.04

# slope at the edge of the lighting table, anything steeper is held there
STEEPEST = 1.1

# lighting table steps across and down, as a power of two. slopes carry a
# quarter step through the blending between grid points and round to a step
# at the end. LEVEL is a level slope in quarter steps, STEEP the most it holds
TABLE_BITS = const(6)
TABLE = const(1 << TABLE_BITS)
LEVEL = const(TABLE * 2)
STEEP = const(TABLE * 4 - 4)

# phase tables run 0-1023 for a full cycle, values x256. PHASE_MASK wraps a phase
STEPS = const(1024)
PHASE_MASK = const(STEPS - 1)
COS = array("i", [int(math.cos(i * 2 * math.pi / STEPS) * 256) for i in range(STEPS)])
SIN = array("i", [int(math.sin(i * 2 * math.pi / STEPS) * 256) for i in range(STEPS)])

# heights are worked out on a grid every SPACING px, with a point beyond each
# edge so every point inside has neighbours to take its slope from
SPACING = const(2)
CELLS = const(128 // SPACING)
POINTS = const(CELLS + 3)
# a row of slopes holds across and down for CELLS + 1 points. a grid row
# covers SPACING rows of px
SLOPE_ROW = const((CELLS + 1) * 2)
GRID_ROW_PIXELS = const(SPACING * 128)

# each boot's sea differs: every wave's length and heading shift by up to
# these, as a share of its length and in degrees
LENGTH_JITTER = 0.15
HEADING_JITTER = 12

# each wave's crests bend, its phase pushed back and forth by slow waves
# across and down of BEND_LENGTHS px. up to BEND_DEPTH radians, drifting over
# BEND_PERIODS seconds. keeps the crests from lining up into a lattice
BEND_LENGTHS = (90, 220)
BEND_DEPTH = (0.4, 0.9)
BEND_PERIODS = (9, 24)

# per wave, height in px x65536 is cos(x + y), x its phase across, y its
# phase down plus travel. that's cos(x) cos(y) - sin(x) sin(y), so cos(x)
# and sin(x) go per column, the rest per row

# each wave's phase at each grid column and row, then its bend's, in table steps
PHASE_ACROSS = array("i", [0] * COUNT * POINTS)
PHASE_DOWN = array("i", [0] * COUNT * POINTS)
BEND_ACROSS = array("i", [0] * COUNT * POINTS)
BEND_DOWN = array("i", [0] * COUNT * POINTS)

# per grid column, the cos then sin of each wave's phase across, x256
COLUMNS = array("i", [0] * POINTS * COUNT * 2)

# per grid row, what multiplies each wave's cos and sin across
ROWS = array("i", [0] * POINTS * COUNT * 2)

# per wave, four pairs of position and speed. they're its travel, bend drift
# across, bend drift down and group cycle. in table steps x65536, speeds per ms
MOTION = array("i", [0] * COUNT * 8)

# per wave, its height in px x256 and its bend's depth in table steps
SHAPE = array("i", [0] * COUNT * 2)


# a speed in table steps per second as a MOTION speed
def motion_speed(per_second):
    return int(per_second * 65536 / 1000)


# radians as phase table steps
def table_steps(radians):
    return int(radians * STEPS / (2 * math.pi))


for wave, (wavelength, heading, steepness) in enumerate(WAVES):
    wavelength *= uniform(1 - LENGTH_JITTER, 1 + LENGTH_JITTER)
    heading += uniform(-HEADING_JITTER, HEADING_JITTER)
    wavenumber = 2 * math.pi / wavelength
    wavenumber_across = wavenumber * math.cos(math.radians(heading))
    wavenumber_down = wavenumber * math.sin(math.radians(heading))

    bend_across = 2 * math.pi / uniform(*BEND_LENGTHS)
    bend_down = 2 * math.pi / uniform(*BEND_LENGTHS)

    for point in range(POINTS):
        position = (point - 1) * SPACING
        slot = wave * POINTS + point
        PHASE_ACROSS[slot] = table_steps(wavenumber_across * position)
        PHASE_DOWN[slot] = table_steps(wavenumber_down * position)
        BEND_ACROSS[slot] = table_steps(bend_across * position)
        BEND_DOWN[slot] = table_steps(bend_down * position)

    speed = math.sqrt(GRAVITY * wavenumber) * SPEED_SPREAD[wave] * STEPS / (2 * math.pi)
    MOTION[wave * 8:wave * 8 + 8] = array("i", [
        int(uniform(0, STEPS) * 65536), motion_speed(speed),
        int(uniform(0, STEPS) * 65536), motion_speed(STEPS / uniform(*BEND_PERIODS)),
        int(uniform(0, STEPS) * 65536), motion_speed(STEPS / uniform(*BEND_PERIODS)),
        int(uniform(0, STEPS) * 65536), motion_speed(STEPS / GROUP_PERIODS[wave % len(GROUP_PERIODS)]),
    ])
    SHAPE[wave * 2] = int(steepness / wavenumber * 256)
    SHAPE[wave * 2 + 1] = table_steps(uniform(*BEND_DEPTH))

# per wave: phase travelled, height in px x256, bend depth, then how far the
# bend has drifted across and down
PARAMS = array("i", [0] * COUNT * 5)

# three rows of heights, and two rows of each grid point's slope across then
# down, in quarter lighting table steps
HEIGHT = array("i", [0] * POINTS * 3)
SLOPES = array("i", [0] * SLOPE_ROW * 2)

# a slope of STEEPEST is half the table in quarter steps, and the height
# difference across a point spans two grid spacings
SLOPE_SHIFT = 0
while (1 << (SLOPE_SHIFT + 1)) <= 2 * SPACING * 65536 * STEEPEST / (TABLE * 2):
    SLOPE_SHIFT += 1


# lighting for every slope across and down
def build_lighting():
    lit = array("I", [0] * TABLE * TABLE)
    middle = TABLE // 2

    sun_x, sun_y, sun_z = SUN_FROM
    size = math.sqrt(sun_x * sun_x + sun_y * sun_y + sun_z * sun_z)
    sun_x, sun_y, sun_z = sun_x / size, sun_y / size, sun_z / size

    # halfway between the sun and the eye above, for the glints
    half_x, half_y, half_z = sun_x, sun_y, sun_z + 1
    size = math.sqrt(half_x * half_x + half_y * half_y + half_z * half_z)
    half_x, half_y, half_z = half_x / size, half_y / size, half_z / size

    for row in range(TABLE):
        slope_down = (row - middle) / middle * STEEPEST
        for column in range(TABLE):
            slope_across = (column - middle) / middle * STEEPEST
            size = math.sqrt(slope_across * slope_across * BUMP * BUMP + slope_down * slope_down * BUMP * BUMP + 1)
            normal_x, normal_y, normal_z = -slope_across * BUMP / size, -slope_down * BUMP / size, 1 / size

            facing = max(0.0, normal_x * sun_x + normal_y * sun_y + normal_z * sun_z)
            towards = max(0.0, normal_x * half_x + normal_y * half_y + normal_z * half_z)
            glint = towards ** SHINE + SHEEN_SHARE * towards ** SHEEN
            reflect = REFLECT + (1 - REFLECT) * (1 - normal_z) ** 5

            shade = (LIGHT_RANGE[0] + (LIGHT_RANGE[1] - LIGHT_RANGE[0]) * facing) * (1 - reflect)
            red = min(255, int(DEEP[0] * shade + SKY[0] * reflect + SUN[0] * glint))
            green = min(255, int(DEEP[1] * shade + SKY[1] * reflect + SUN[1] * glint))
            blue = min(255, int(DEEP[2] * shade + SKY[2] * reflect + SUN[2] * glint))
            lit[row * TABLE + column] = 0xff000000 | (blue << 16) | (green << 8) | red

    return lit


# the lighting table, kept beside the plugin as it takes seconds to build
def load_lighting():
    folder = globals().get("__file__", "/lib/plugins/ocean/__init__.py").rsplit("/", 1)[0]
    key = crc32(repr((DEEP, SKY, SUN, SUN_FROM, SHINE, SHEEN, SHEEN_SHARE, LIGHT_RANGE, BUMP, REFLECT, STEEPEST, TABLE)).encode())
    name = "lit-%08x.bin" % key
    path = f"{folder}/{name}"

    lit = bytearray(TABLE * TABLE * 4)
    try:
        with open(path, "rb") as file:
            if file.readinto(lit) == len(lit):
                return lit
    except OSError:
        pass

    lit = build_lighting()

    # tables for other settings would only ever be stale
    for other in os.listdir(folder):
        if other.startswith("lit-") and other != name:
            os.remove(f"{folder}/{other}")
    try:
        with open(path, "wb") as file:
            file.write(lit)
    except OSError:
        # no room, so it builds again next time
        pass

    return lit


LIT = load_lighting()

# how much sound can raise each wave: the long ones follow the bass, the
# short ones the treble, all of them the loudness
SWELL_LIFT = 0.5
CHOP_LIFT = 0.9
LOUD_LIFT = 0.3

# how quickly the sea follows the sound, rising then falling, per second
FOLLOW = (0.8, 0.4)


# per grid column, each wave's cos and sin of its bent phase across
@micropython.viper
def columns(phase: ptr32, bend: ptr32, params: ptr32, cos: ptr32,
            sin: ptr32, out: ptr32, points: int, count: int):
    point = 0
    while point < points:
        wave = 0
        while wave < count:
            at = wave * points + point
            depth = int(params[wave * 5 + 2])
            bent = int(phase[at]) + ((depth * int(sin[(int(bend[at]) + int(params[wave * 5 + 3])) & PHASE_MASK])) >> 8)
            out_at = (point * count + wave) * 2
            out[out_at] = int(cos[bent & PHASE_MASK])
            out[out_at + 1] = int(sin[bent & PHASE_MASK])
            wave += 1
        point += 1


# per grid row, what multiplies each wave's column cos and sin. that's its
# height times the cos, and minus the sin, of its bent phase down plus travel
@micropython.viper
def rows(phase: ptr32, bend: ptr32, params: ptr32, cos: ptr32,
         sin: ptr32, out: ptr32, points: int, count: int):
    point = 0
    while point < points:
        wave = 0
        while wave < count:
            at = wave * points + point
            depth = int(params[wave * 5 + 2])
            bent = int(phase[at]) + int(params[wave * 5]) + ((depth * int(sin[(int(bend[at]) + int(params[wave * 5 + 4])) & PHASE_MASK])) >> 8)
            height = int(params[wave * 5 + 1])
            out_at = (point * count + wave) * 2
            out[out_at] = (height * int(cos[bent & PHASE_MASK])) >> 8
            out[out_at + 1] = -((height * int(sin[bent & PHASE_MASK])) >> 8)
            wave += 1
        point += 1


# row by row: the next row of heights, the slopes for the row above, then the
# 2 x 2 pixel blocks above that, lit from their corners' slopes. three rows of
# heights and two of slopes stay in cache
@micropython.viper
def render(across: ptr32, rows: ptr32, lit: ptr32, pixels: ptr32,
           heights: ptr32, slopes: ptr32, shift: int):
    # where the three rows of heights and two rows of slopes start. they swap
    # round as it goes down
    up = 0
    middle = POINTS
    down = 2 * POINTS
    upper = 0
    lower = SLOPE_ROW
    grid_row = 0
    while grid_row < POINTS:
        # heights for this grid row go where the row two above was
        at = grid_row * ROW_TERMS
        wave0_cos = int(rows[at])
        wave0_sin = int(rows[at + 1])
        wave1_cos = int(rows[at + 2])
        wave1_sin = int(rows[at + 3])
        wave2_cos = int(rows[at + 4])
        wave2_sin = int(rows[at + 5])
        wave3_cos = int(rows[at + 6])
        wave3_sin = int(rows[at + 7])
        wave4_cos = int(rows[at + 8])
        wave4_sin = int(rows[at + 9])
        wave5_cos = int(rows[at + 10])
        wave5_sin = int(rows[at + 11])
        column = 0
        point = down
        while point < down + POINTS:
            heights[point] = (int(across[column]) * wave0_cos + int(across[column + 1]) * wave0_sin
                              + int(across[column + 2]) * wave1_cos + int(across[column + 3]) * wave1_sin
                              + int(across[column + 4]) * wave2_cos + int(across[column + 5]) * wave2_sin
                              + int(across[column + 6]) * wave3_cos + int(across[column + 7]) * wave3_sin
                              + int(across[column + 8]) * wave4_cos + int(across[column + 9]) * wave4_sin
                              + int(across[column + 10]) * wave5_cos + int(across[column + 11]) * wave5_sin)
            column += ROW_TERMS
            point += 1

        if grid_row >= 2:
            # slopes for the grid row above this one, from the rows either side of it
            slope_at = lower
            point = 1
            while point <= CELLS + 1:
                # in quarter steps, held to the table's last step
                slope_across = LEVEL + ((int(heights[middle + point + 1]) - int(heights[middle + point - 1])) >> shift)
                slope_down = LEVEL + ((int(heights[down + point]) - int(heights[up + point])) >> shift)
                if slope_across < 0:
                    slope_across = 0
                elif slope_across > STEEP:
                    slope_across = STEEP
                if slope_down < 0:
                    slope_down = 0
                elif slope_down > STEEP:
                    slope_down = STEEP
                slopes[slope_at] = slope_across
                slopes[slope_at + 1] = slope_down
                slope_at += 2
                point += 1

            if grid_row >= 3:
                pixel = (grid_row - 3) * GRID_ROW_PIXELS
                above = upper
                below = lower
                while above < upper + CELLS * 2:
                    # each 2 x 2 block, lit from the slopes at its corners
                    top_left_across = int(slopes[above])
                    top_left_down = int(slopes[above + 1])
                    top_right_across = int(slopes[above + 2])
                    top_right_down = int(slopes[above + 3])
                    bottom_left_across = int(slopes[below])
                    bottom_left_down = int(slopes[below + 1])
                    bottom_right_across = int(slopes[below + 2])
                    bottom_right_down = int(slopes[below + 3])
                    # blended in quarter steps, rounded to the nearest step
                    pixels[pixel] = lit[(((top_left_down + 2) >> 2) << TABLE_BITS) | ((top_left_across + 2) >> 2)]
                    pixels[pixel + 1] = lit[(((top_left_down + top_right_down + 4) >> 3) << TABLE_BITS)
                                            | ((top_left_across + top_right_across + 4) >> 3)]
                    pixels[pixel + 128] = lit[(((top_left_down + bottom_left_down + 4) >> 3) << TABLE_BITS)
                                              | ((top_left_across + bottom_left_across + 4) >> 3)]
                    pixels[pixel + 129] = lit[(((top_left_down + top_right_down + bottom_left_down + bottom_right_down + 8) >> 4) << TABLE_BITS)
                                              | ((top_left_across + top_right_across + bottom_left_across + bottom_right_across + 8) >> 4)]
                    pixel += 2
                    above += 2
                    below += 2

            swap = upper
            upper = lower
            lower = swap

        swap = up
        up = middle
        middle = down
        down = swap
        grid_row += 1


# moves every wave on by elapsed ms and fills PARAMS. swell and chop are how
# much sound lifts the long and the short waves, x256
@micropython.viper
def advance(motion: ptr32, shape: ptr32, params: ptr32, sin: ptr32,
            elapsed: int, swell: int, chop: int, count: int):
    wave = 0
    while wave < count:
        motion_at = wave * 8
        pair = 0
        while pair < 8:
            motion[motion_at + pair] = (int(motion[motion_at + pair]) + int(motion[motion_at + pair + 1]) * elapsed) & 0x3ffffff
            pair += 2

        group = GROUP_LOW + (((256 - GROUP_LOW) * (256 + int(sin[int(motion[motion_at + 6]) >> 16]))) >> 9)
        lift = swell if wave < (count >> 1) else chop

        params_at = wave * 5
        params[params_at] = int(motion[motion_at]) >> 16
        params[params_at + 1] = (((int(shape[wave * 2]) * group) >> 8) * lift) >> 8
        params[params_at + 2] = int(shape[wave * 2 + 1])
        params[params_at + 3] = int(motion[motion_at + 2]) >> 16
        params[params_at + 4] = int(motion[motion_at + 4]) >> 16
        wave += 1


last = time.ticks_ms()

# the smoothed loudness, bass and treble
loud = 0.0
bass = 0.0
treble = 0.0


def update():
    global last, loud, bass, treble

    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, last)
    last = now

    # the share of the way to its target each follower moves this frame
    rise = 1 - math.exp(-FOLLOW[0] * elapsed / 1000)
    fall = 1 - math.exp(-FOLLOW[1] * elapsed / 1000)

    if hearing is not None and hearing.active():
        bands = hearing.spectrum()
        targets = (hearing.level(), (bands[0] + bands[1] + bands[2] + bands[3]) / 4,
                   (bands[9] + bands[10] + bands[11] + bands[12] + bands[13]) / 5)
    else:
        targets = (0, 0, 0)

    loud += (targets[0] - loud) * (rise if targets[0] > loud else fall)
    bass += (targets[1] - bass) * (rise if targets[1] > bass else fall)
    treble += (targets[2] - treble) * (rise if targets[2] > treble else fall)

    # the first half of the waves are swell, the rest chop
    swell = int((1 + loud * LOUD_LIFT + bass * SWELL_LIFT) * 256)
    chop = int((1 + loud * LOUD_LIFT + treble * CHOP_LIFT) * 256)
    advance(MOTION, SHAPE, PARAMS, SIN, elapsed, swell, chop, COUNT)

    columns(PHASE_ACROSS, BEND_ACROSS, PARAMS, COS, SIN, COLUMNS, POINTS, COUNT)
    rows(PHASE_DOWN, BEND_DOWN, PARAMS, COS, SIN, ROWS, POINTS, COUNT)
    render(COLUMNS, ROWS, LIT, memoryview(screen), HEIGHT, SLOPES, SLOPE_SHIFT)
