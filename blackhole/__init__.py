import math
import time
import micropython
from array import array
from random import random, randrange

import timezones

screen.antialias = image.X4

WIDTH = const(128)
HEIGHT = const(128)
CENTRE = 64

# sizes in pixels from the centre
SHADOW_RADIUS = 17.0
DISC_INNER = 20.0
DISC_OUTER = 60.0
EINSTEIN_RADIUS = 23.0
MARKER_ORBIT = 61

# the disc carries on inside the hole and fades out by INFALL_END
INFALL_END = 5.0
INFALL_BRIGHTNESS = 0.8
# a thin flipped copy of the disc inside the hole, turning the other way
SECOND_IMAGE_RADIUS = 13.5
SECOND_IMAGE_HALF_WIDTH = 1.0
SECOND_IMAGE_BRIGHTNESS = 0.6
SECOND_IMAGE_SOURCE = 40  # the ring it's a copy of

# the disc texture has one row per ring of pixels, from FIRST_RING out
FIRST_RING = const(4)
RINGS = const(60)

# angles are 256 to a turn. the inner edge spins about a tenth of a turn a second
INNER_SPIN = 26
REFERENCE_RING = 44
# each copy of the texture shears for this long before it's swapped out
SHEAR_SECONDS = 24.0

# byte scales. a texel byte of 255 is 1.25 and a disc byte of 255 is ~1.9
TEXEL_SCALE = 204
DISC_SCALE = 136
# how far a copy's texture jumps round when it resets, so it doesn't come back the same
TEXTURE_JUMP = const(97)

# stars fade out where the disc is brighter than this
STAR_FADE = const(212)
OPAQUE = const(-16777216)

# disc texture. fractal noise stretched round the turn into streaks, plus two loose spiral arms
NOISE_CELL = 4  # rings per cell of the coarsest noise
NOISE_STRETCH = 4  # cells are this many times wider round the turn
NOISE_REPEAT = 16  # cells to a turn, so it repeats every 16 x 4 x 4 = 256 texels
noise = image(256, RINGS)
# 3 octaves, each half the size of the last and 0.4 as strong
noise.pen = brush.fractal(NOISE_CELL, 3, 0.4, NOISE_REPEAT, randrange(65536), mat3().scale(NOISE_STRETCH, 1))
noise.clear()
grains = memoryview(noise)  # four bytes a texel, red first

# x127
ARM_COS = [int(127 * math.cos(column * math.pi / 64)) for column in range(256)]
ARM_SIN = [int(127 * math.sin(column * math.pi / 64)) for column in range(256)]
# brightens the bright bits and pushes the gaps down. byte in, byte out
CURVE = bytes(min(255, int((0.15 + 1.1 * (level / 255) ** 1.8) * TEXEL_SCALE)) for level in range(256))

# whole numbers in here, as every float sum allocates and the bake would take seconds
TEXTURE = bytearray(RINGS * 256)
for row in range(RINGS):
    grain = [grains[(row * 256 + column) * 4] for column in range(256)]
    lowest = min(grain)
    spread = max(max(grain) - lowest, 1)

    # the arms wind round further the further out they are. x256
    twist = 9 * math.log(row + FIRST_RING)
    twist_cos = int(256 * math.cos(twist))
    twist_sin = int(256 * math.sin(twist))
    for column in range(256):
        arms = 128 + ((ARM_COS[column] * twist_cos + ARM_SIN[column] * twist_sin) >> 9)
        stretched = (grain[column] - lowest) * 255 // spread
        TEXTURE[row * 256 + column] = CURVE[min(255, (3 * stretched + 2 * arms) // 5)]
grains = None
noise = None

# how much faster or slower than the reference ring each ring turns, angle units a second x256
SHEAR = array("i", [0] * RINGS)
reference_spin = INNER_SPIN * (DISC_INNER / REFERENCE_RING) ** 1.5
for row in range(RINGS):
    ring_spin = INNER_SPIN * (DISC_INNER / max(row + FIRST_RING, DISC_INNER)) ** 1.5
    SHEAR[row] = int((ring_spin - reference_spin) * 256)

# a sky of stars that wraps every 128 pixels. only used while baking
STARFIELD = bytearray(128 * 128)
for _ in range(90):
    STARFIELD[randrange(128 * 128)] = int(255 * (0.3 + 0.7 * random() ** 2))

# everything that only depends on distance, in quarter pixels out to the corners
QUARTERS = 4
REACH = 92 * QUARTERS
disc_by_distance = []
photon_by_distance = []
bend_by_distance = []
magnify_by_distance = []
for quarter in range(REACH):
    distance = max((quarter + 0.5) / QUARTERS, 0.5)
    if distance > SHADOW_RADIUS:
        outwards = (distance - DISC_INNER) / (DISC_OUTER - DISC_INNER)
        falloff = 1.5 * max(0, 1 - outwards) ** 2.2
        edge = min(max((distance - DISC_INNER + 1.5) / 3, 0), 1)
        disc_by_distance.append(int(falloff * edge * DISC_SCALE))
    elif abs(distance - SECOND_IMAGE_RADIUS) < SECOND_IMAGE_HALF_WIDTH:
        across_band = (distance - SECOND_IMAGE_RADIUS) / SECOND_IMAGE_HALF_WIDTH
        disc_by_distance.append(int(SECOND_IMAGE_BRIGHTNESS * (1 - across_band * across_band) * DISC_SCALE))
    else:
        inwards = max(0, (distance - INFALL_END) / (SHADOW_RADIUS - INFALL_END))
        disc_by_distance.append(int(INFALL_BRIGHTNESS * inwards ** 1.4 * DISC_SCALE))
    photon_by_distance.append(int(255 * math.exp(-((distance - SHADOW_RADIUS - 0.6) / 0.8) ** 2)))
    # light from behind bends round the hole. the sky shows up where it lands
    bent = distance - EINSTEIN_RADIUS * EINSTEIN_RADIUS / distance
    bend_by_distance.append(bent / distance)
    closeness = 1.2 * EINSTEIN_RADIUS / max(abs(bent), 3)
    magnify = min(max(closeness, 1), 4)
    magnify_by_distance.append(min(255, int(magnify * 64)))  # x64

# the left side is coming towards us so it's a bit brighter. x256, by angle
DISC_DOPPLER = [int(256 * (1 + 0.3 * math.cos((angle / 256 - 0.75) * 2 * math.pi))) for angle in range(256)]
PHOTON_DOPPLER = [int(256 * 0.85 + 0.15 * doppler) for doppler in DISC_DOPPLER]

# 12, 3, 6 and 9 o'clock
#          x                      y                      brightness
MARKERS = [(CENTRE, CENTRE - MARKER_ORBIT, 230),
           (CENTRE + MARKER_ORBIT, CENTRE, 90),
           (CENTRE, CENTRE + MARKER_ORBIT, 90),
           (CENTRE - MARKER_ORBIT, CENTRE, 90)]
MARKER_SIZE = 1.2

# five bytes a pixel, all in one table so the viper pass reads it in one sweep.
# glint is the stars and markers, added on top in a pale blue
STRIDE = const(5)
RING = const(0)
ANGLE = const(1)
DISC = const(2)  # x DISC_SCALE
PHOTON = const(3)
GLINT = const(4)
PIXEL_TABLE = bytearray(WIDTH * HEIGHT * STRIDE)

# the four quarters of the screen mirror each other. so the float maths is done for the
# top right quarter, and each result is written to all four with the angle flipped to match
for y in range(HEIGHT // 2):
    for x in range(WIDTH // 2, WIDTH):
        across = x + 0.5 - CENTRE
        down = y + 0.5 - CENTRE
        distance = math.sqrt(across * across + down * down)
        quarter = min(int(distance * QUARTERS), REACH - 1)
        # clockwise from 12 o'clock, so 0 to 63 in this quarter
        angle = int(math.atan2(across, -down) / (2 * math.pi) * 256)
        ring = min(max(int(distance) - FIRST_RING, 0), RINGS - 1)
        is_second_image = abs(distance - SECOND_IMAGE_RADIUS) < SECOND_IMAGE_HALF_WIDTH
        if is_second_image:
            ring = SECOND_IMAGE_SOURCE - FIRST_RING
        disc = disc_by_distance[quarter]
        photon = photon_by_distance[quarter]
        has_stars = distance > SHADOW_RADIUS + 1
        bend = bend_by_distance[quarter]
        star_across = int(across * bend)
        star_down = int(down * bend)
        gain = magnify_by_distance[quarter]  # x64

        # bit 1 of mirror flips left to right and bit 2 flips top to bottom.
        # no tuples here, as small allocations on this heap are slow enough to take the bake to 26 s
        for mirror in range(4):
            column = x
            row = y
            mirrored = angle
            star_x = CENTRE + star_across
            star_y = CENTRE + star_down
            if mirror & 1:
                column = WIDTH - 1 - x
                mirrored = -mirrored
                star_x = CENTRE - star_across
            if mirror & 2:
                row = HEIGHT - 1 - y
                mirrored = 128 - mirrored
                star_y = CENTRE - star_down
            mirrored &= 255
            base = (row * WIDTH + column) * STRIDE
            PIXEL_TABLE[base + RING] = ring
            PIXEL_TABLE[base + ANGLE] = mirrored
            if is_second_image:
                # a backwards angle flips the picture, and the spin then runs the other way
                PIXEL_TABLE[base + ANGLE] = -mirrored & 255
            PIXEL_TABLE[base + DISC] = min(255, (disc * DISC_DOPPLER[mirrored]) >> 8)
            PIXEL_TABLE[base + PHOTON] = min(255, (photon * PHOTON_DOPPLER[mirrored]) >> 8)
            if has_stars:
                star = STARFIELD[(star_y & 127) * 128 + (star_x & 127)]
                PIXEL_TABLE[base + GLINT] = min(255, (star * gain) >> 6)

# a soft dot in the few pixels round each marker
for marker_x, marker_y, brightness in MARKERS:
    for y in range(marker_y - 3, min(marker_y + 4, HEIGHT)):
        for x in range(marker_x - 3, min(marker_x + 4, WIDTH)):
            gap_x = x + 0.5 - marker_x
            gap_y = y + 0.5 - marker_y
            spread = (gap_x * gap_x + gap_y * gap_y) / (MARKER_SIZE * MARKER_SIZE)
            glint = (y * WIDTH + x) * STRIDE + GLINT
            PIXEL_TABLE[glint] = max(PIXEL_TABLE[glint], int(brightness * math.exp(-spread / 2)))
STARFIELD = None

# dark red through orange to white hot
#              heat               lightness chroma hue
HEAT_STOPS = [(0.0, color.oklch(20, 14, 19)),
              (0.15, color.oklch(70, 89, 26)),
              (0.35, color.oklch(119, 153, 35)),
              (0.6, color.oklch(172, 135, 46)),
              (0.85, color.oklch(221, 24, 57)),
              (1.0, color.oklch(249, 14, 64))]
# p is packed like the screen stores a pixel: 0xaabbggrr
PALETTE = array("i", [shade.fit().p for shade in color.ramp(HEAT_STOPS, 256)])
PALETTE[0] = OPAQUE

# filled in each frame for the two copies of the texture
OFFSETS_A = bytearray(RINGS)
OFFSETS_B = bytearray(RINGS)

# viper takes four args max so these ride together. ages are s x256 and the weight is x256
SPIN = const(0)
AGE_A = const(1)
AGE_B = const(2)
WEIGHT_A = const(3)
SHIFT_A = const(4)
SHIFT_B = const(5)
PARAMS = array("i", [0] * 6)


@micropython.viper
def draw_disc(pixels: ptr32, params: ptr32):  # noqa: F821
    table = ptr8(PIXEL_TABLE)  # noqa: F821
    texture = ptr8(TEXTURE)  # noqa: F821
    shear = ptr32(SHEAR)  # noqa: F821
    palette = ptr32(PALETTE)  # noqa: F821
    offsets_a = ptr8(OFFSETS_A)  # noqa: F821
    offsets_b = ptr8(OFFSETS_B)  # noqa: F821

    spin = params[SPIN]
    age_a = params[AGE_A]
    age_b = params[AGE_B]
    weight_a = params[WEIGHT_A]
    weight_b = 256 - weight_a
    shift_a = params[SHIFT_A]
    shift_b = params[SHIFT_B]

    # each ring turns at its own speed, but only shears for one copy's age
    for ring in range(RINGS):
        rate = shear[ring]
        offsets_a[ring] = (spin + shift_a + ((rate * age_a) >> 16)) & 255
        offsets_b[ring] = (spin + shift_b + ((rate * age_b) >> 16)) & 255

    for i in range(WIDTH * HEIGHT):
        base = i * STRIDE
        heat = table[base + PHOTON]
        disc = table[base + DISC]
        if disc:
            ring = table[base + RING]
            angle = table[base + ANGLE]
            row = ring << 8
            texel_a = texture[row + ((angle - offsets_a[ring]) & 255)]
            texel_b = texture[row + ((angle - offsets_b[ring]) & 255)]
            texel = (texel_a * weight_a + texel_b * weight_b) >> 8
            heat += (texel * disc) >> 7
            if heat > 255:
                heat = 255
        colour = palette[heat]

        glint = table[base + GLINT]
        if glint and heat < STAR_FADE:
            glint = glint * (STAR_FADE - heat) // STAR_FADE
            red = (colour & 255) + ((glint * 160) >> 8)
            green = ((colour >> 8) & 255) + ((glint * 215) >> 8)
            blue = ((colour >> 16) & 255) + glint
            if red > 255:
                red = 255
            if green > 255:
                green = 255
            if blue > 255:
                blue = 255
            colour = OPAQUE | (blue << 16) | (green << 8) | red
        pixels[i] = colour


DOT = shape.regular_polygon(0, 0, 1, 16)

HOUR_ORBIT = 38
HOUR_SIZE = 3.0
HOUR_TRAIL = 55  # degrees
MINUTE_ORBIT = 51
MINUTE_SIZE = 2.2
MINUTE_TRAIL = 45
TRAIL_STEPS = 12

# red, green, blue
HOUR_TINT = (70, 200, 255)
MINUTE_TINT = (235, 240, 255)
HOUR_HALO = color.rgb(*HOUR_TINT, 80)
HOUR_CORE = color.rgb(130, 230, 255)
MINUTE_HALO = color.rgb(*MINUTE_TINT, 80)
MINUTE_CORE = color.rgb(255, 255, 255)


# a crescent behind a body at 12 o'clock, centred on the hole. it thins towards the tail
def make_trail(orbit, size, trail):
    outer_edge = []
    inner_edge = []
    for step in range(TRAIL_STEPS + 1):
        behind = step / TRAIL_STEPS
        at = math.radians(-trail * behind)
        half_width = size * (1 - 0.7 * behind)
        outer_edge.append(((orbit + half_width) * math.sin(at), -(orbit + half_width) * math.cos(at)))
        inner_edge.append(((orbit - half_width) * math.sin(at), -(orbit - half_width) * math.cos(at)))
    # out along the outside to the tail, then back along the inside
    points = array("f")
    for point_x, point_y in outer_edge + inner_edge[::-1]:
        points.append(point_x)
        points.append(point_y)
    return shape.custom(points)


# fades in clockwise from the tail. a brush turns with the shape it's drawn in, so this is
# set up round the trail's own centre, with the body at 12 o'clock
def make_fade(trail, tint):
    tail = math.radians(-trail)
    return brush.gradient(brush.CONICAL, 0, 0, math.sin(tail), -math.cos(tail),
                          [(0, color.rgb(*tint, 0)), (trail / 360, color.rgb(*tint, 170))])


HOUR_TRAIL_SHAPE = make_trail(HOUR_ORBIT, HOUR_SIZE, HOUR_TRAIL)
MINUTE_TRAIL_SHAPE = make_trail(MINUTE_ORBIT, MINUTE_SIZE, MINUTE_TRAIL)
HOUR_FADE = make_fade(HOUR_TRAIL, HOUR_TINT)
MINUTE_FADE = make_fade(MINUTE_TRAIL, MINUTE_TINT)


def draw_body(degrees, orbit, size, trail_shape, fade, halo, core):
    screen.pen = fade
    trail_shape.transform = mat3.trs(CENTRE, CENTRE, degrees, 1)
    screen.shape(trail_shape)

    at = math.radians(degrees)
    body_x = CENTRE + orbit * math.sin(at)
    body_y = CENTRE - orbit * math.cos(at)
    screen.pen = halo
    DOT.transform = mat3.trs(body_x, body_y, 0, size * 2)
    screen.shape(DOT)
    screen.pen = core
    DOT.transform = mat3.trs(body_x, body_y, 0, size)
    screen.shape(DOT)


spin = 0.0
age = 0.0
shift_a = 0
shift_b = TEXTURE_JUMP // 2
last = time.ticks_ms()


def update():
    global spin, age, shift_a, shift_b, last

    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, last) / 1000
    last = now

    spin = (spin + reference_spin * elapsed) % 256

    # copy b runs half a cycle behind copy a. each one jumps to fresh texture as it resets
    age_b_before = (age + SHEAR_SECONDS / 2) % SHEAR_SECONDS
    age += elapsed
    if age >= SHEAR_SECONDS:
        age %= SHEAR_SECONDS
        shift_a = (shift_a + TEXTURE_JUMP) & 255
    age_b = (age + SHEAR_SECONDS / 2) % SHEAR_SECONDS
    if age_b < age_b_before:
        shift_b = (shift_b + TEXTURE_JUMP) & 255

    # copy a is invisible as it resets and fully showing halfway through
    weight_a = 1 - abs(age / SHEAR_SECONDS * 2 - 1)

    PARAMS[SPIN] = int(spin)
    PARAMS[AGE_A] = int(age * 256)
    PARAMS[AGE_B] = int(age_b * 256)
    PARAMS[WEIGHT_A] = int(weight_a * 256)
    PARAMS[SHIFT_A] = shift_a
    PARAMS[SHIFT_B] = shift_b
    draw_disc(memoryview(screen), PARAMS)

    _, _, _, hour, minute, second, _, _ = timezones.localtime()
    draw_body((hour % 12) * 30 + minute / 2, HOUR_ORBIT, HOUR_SIZE, HOUR_TRAIL_SHAPE, HOUR_FADE, HOUR_HALO, HOUR_CORE)
    draw_body(minute * 6 + second / 10, MINUTE_ORBIT, MINUTE_SIZE, MINUTE_TRAIL_SHAPE, MINUTE_FADE,
              MINUTE_HALO, MINUTE_CORE)
