import math
import time
import micropython
from array import array
from micropython import const
from random import getrandbits

# rows above HORIZON are sky, below it sea. SEA_STRIDE is one sea row's
# numbers in SEA, 2 + 4 per wave
HORIZON = const(84)
SEA_ROWS = const(128 - HORIZON)
SEA_STRIDE = const(14)

# sky at the top and at the horizon, the sea at the horizon and close by
SKY_TOP = (5, 7, 32)
SKY_HORIZON = (29, 51, 112)
SEA_FAR = (5, 8, 22)
SEA_NEAR = (2, 5, 14)

# the moon: its middle and radius in px and its colour. then its halo's
# colour, reach in px past its edge and strength. MOON_BOX is the square
# they're drawn in
MOON_X = const(90)
MOON_Y = const(43)
MOON_RADIUS = const(11)
MOON = (195, 193, 180)
HALO = (120, 130, 170)
HALO_REACH = const(10)
HALO_STRENGTH = 0.55
MOON_BOX = const((MOON_RADIUS + HALO_REACH) * 2 + 3)

# clouds: colour in the dark and lit by the moon, each layer's drift in px a
# second. then how much the far layer shows and the band of rows they keep to
CLOUD_DARK = (34, 40, 66)
CLOUD_LIT = (118, 122, 140)
DRIFT = (2.2, 4.0)
FAR_LAYER = 0.6
CLOUD_BAND = (6, 64)
# the far layer reads the texture this many rows down, so it doesn't match the near one
FAR_ROW_OFFSET = const(29)

# each row below the horizon is a distance out, FOCAL px giving one unit of
# height per unit of distance. each wave: its length and heading in those
# units (90 is straight at us). then its steepness
FOCAL = 110
WAVES = [(3.0, 80, 0.07), (1.6, 58, 0.055), (0.85, 112, 0.04)]

# how far the sky's reflection shifts per unit of slope in px, across and up.
# then how much the water reflects close by and near the horizon. steep faces
# far out stretch the moon's reflection into a long path
SHIFT = (70, 260)
REFLECT = (0.35, 0.92)

STARS = const(90)

# glow around the brightest glints: bloom(threshold, intensity, radius, strength)
BLOOM = (205, 255, 5, 1.4)

# how much loudness makes the waves steeper
LOUD_WAVES = 0.6

# sine table: 1024 steps a turn, values x256
SIN = array("i", [int(math.sin(i * 2 * math.pi / 1024) * 256) for i in range(1024)])

# 0xff000000, a pixel's alpha byte fully on, written signed for viper
OPAQUE = const(-16777216)


def pack(rgb):
    return 0xff000000 | (int(rgb[2]) << 16) | (int(rgb[1]) << 8) | int(rgb[0])


# from colour start toward colour end, amount 0 to 1
def mix(start, end, amount):
    return [start[channel] + (end[channel] - start[channel]) * amount for channel in range(3)]


SKY = array("I", [pack(mix(SKY_TOP, SKY_HORIZON, (y / (HORIZON - 1)) ** 1.6)) for y in range(HORIZON)])

# stars: x, y and twinkle phase, kept above the horizon
SCENE = array("i", [0] * STARS * 3)
for star in range(STARS):
    SCENE[star * 3] = getrandbits(7)
    SCENE[star * 3 + 1] = getrandbits(7) % (HORIZON - 6)
    SCENE[star * 3 + 2] = getrandbits(10)


# value noise for the clouds: a hashed lattice blended smoothly, three
# octaves, stretched 4x wider than tall so it comes out as wisps. wraps across
# its width
@micropython.viper
def noise(out: ptr8, width: int, height: int, seed: int):
    y = 0
    while y < height:
        x = 0
        while x < width:
            total = 0
            octave = 0
            while octave < 3:
                cell_width = 64 >> octave
                cell_height = 16 >> octave
                cells_across = width // cell_width
                cell_x = x // cell_width
                cell_y = y // cell_height
                # how far into the cell, 0-256, eased so the cells blend smoothly
                blend_x = ((x - cell_x * cell_width) << 8) // cell_width
                blend_y = ((y - cell_y * cell_height) << 8) // cell_height
                blend_x = (blend_x * blend_x * (768 - 2 * blend_x)) >> 16
                blend_y = (blend_y * blend_y * (768 - 2 * blend_y)) >> 16
                corner = 0
                values = 0
                while corner < 4:
                    corner_x = (cell_x + (corner & 1)) % cells_across
                    corner_y = cell_y + (corner >> 1)
                    hashed = (corner_x * 1619 + corner_y * 31337 + seed * 1013 + octave * 7919) * 1664525 + 1013904223
                    hashed = (hashed * 1664525 + 1013904223) >> 16
                    value = hashed & 255
                    weight_x = blend_x if corner & 1 else 256 - blend_x
                    weight_y = blend_y if corner >> 1 else 256 - blend_y
                    values += (value * weight_x * weight_y) >> 16
                    corner += 1
                total += values >> octave
                octave += 1
            # three octaves weigh 1, 1/2 and 1/4
            out[y * width + x] = (total * 4) // 7
            x += 1
        y += 1


# cloud texture, the noise turned to how much cloud there is, 0-255: thin
# wisps where the noise peaks, kept to their band of sky
CLOUD_WIDTH = const(256)
CLOUDS = bytearray(CLOUD_WIDTH * HORIZON)
noise(CLOUDS, CLOUD_WIDTH, HORIZON, getrandbits(10))
band_top, band_bottom = CLOUD_BAND
for y in range(HORIZON):
    band = max(0.0, math.sin(math.pi * (y - band_top) / (band_bottom - band_top))) if band_top <= y <= band_bottom else 0
    for x in range(CLOUD_WIDTH):
        value = CLOUDS[y * CLOUD_WIDTH + x]
        CLOUDS[y * CLOUD_WIDTH + x] = int(max(0, min(255, (value - 112) * 4)) * band)

# how lit a cloud is by its squared distance from the moon, / 128, 0-256
LIT = array("i", [int(256 * math.exp(-math.sqrt(distance * 128) / 16)) for distance in range(256)])


# the moon, per pixel of MOON_BOX: colour and how much it covers. maria, a
# few craters, a darker rim and a soft edge
def moon_texture():
    texture = array("I", [0] * MOON_BOX * MOON_BOX)
    maria = bytearray(64 * 64)
    noise(maria, 64, 64, getrandbits(10))
    craters = [(getrandbits(5) - 16, getrandbits(5) - 16, 1 + getrandbits(2)) for _ in range(7)]
    middle = MOON_BOX / 2
    for y in range(MOON_BOX):
        for x in range(MOON_BOX):
            offset_x = x + 0.5 - middle
            offset_y = y + 0.5 - middle
            distance = math.sqrt(offset_x * offset_x + offset_y * offset_y)
            cover = max(0.0, min(1.0, MOON_RADIUS - distance + 0.5))
            # its halo, fading out past its edge, under the moon's edge
            halo = HALO_STRENGTH * max(0.0, min(1.0, 1 - (distance - MOON_RADIUS) / HALO_REACH)) ** 2
            if not cover:
                if halo > 0:
                    texture[y * MOON_BOX + x] = (int(halo * 255) << 24) | (HALO[2] << 16) | (HALO[1] << 8) | HALO[0]
                continue
            # how far the surface bulges toward us, 1 in the middle and 0 at the rim
            bulge = math.sqrt(max(0.0, 1 - (distance / MOON_RADIUS) ** 2))
            light = 0.62 + 0.38 * bulge ** 0.4
            mare = maria[(y * 64 // MOON_BOX) * 64 + x * 64 // MOON_BOX]
            if mare > 125:
                light *= 1 - min(0.4, (mare - 125) / 160)
            for crater_x, crater_y, crater_radius in craters:
                from_crater = math.sqrt((offset_x - crater_x * 0.6) ** 2 + (offset_y - crater_y * 0.6) ** 2)
                if from_crater < crater_radius:
                    light *= 0.88
                elif from_crater < crater_radius + 0.8:
                    light *= 1.06
            rgb = [min(255, channel * light) for channel in MOON]
            # where the moon only partly covers, it lies over its halo
            under = halo * (1 - cover)
            alpha = cover + under
            rgb = [(rgb[channel] * cover + HALO[channel] * under) / alpha for channel in range(3)]
            texture[y * MOON_BOX + x] = (int(alpha * 255) << 24) | (int(rgb[2]) << 16) | (int(rgb[1]) << 8) | int(rgb[0])
    return texture


MOON_TEXTURE = moon_texture()


# points along a natural looking ridge from left to right, at most height px
# above the horizon. overlapping slow waves with random phases, shaped by
# lumps(x) from 0 to 1 if given, else the same height all along
def outline(left, right, height, lumps=None, step=3):
    phases = [getrandbits(10) / 1024 * 2 * math.pi for _ in range(3)]
    points = []
    x = left
    while x <= right + step:
        wave = (0.5 * math.sin(x * 0.045 + phases[0]) + 0.3 * math.sin(x * 0.11 + phases[1])
                + 0.2 * math.sin(x * 0.27 + phases[2]))
        lumpiness = lumps(x) if lumps else 1
        points.append(vec2(min(x, right), HORIZON - height * lumpiness * (0.75 + 0.25 * wave)))
        x += step
    return points


# the far hills and the nearer shore, drawn once, antialiased, on a clear
# background to lay over the sky and sea
def coast():
    land = image(128, 128)
    land.antialias = image.X4
    land.pen = color.rgb(0, 0, 0, 0)
    land.clear()

    # low hills far off right along the horizon, faint in the haze
    land.pen = color.rgb(12, 16, 34)
    hills = outline(0, 128, 5)
    land.shape(shape.custom([vec2(0, HORIZON + 1)] + hills + [vec2(128, HORIZON + 1)]))

    # the nearer shore on the left, rolling down into the sea
    land.pen = color.rgb(4, 5, 11)
    reach = 58 + getrandbits(4)

    def falls(x):
        along = min(1.0, max(0.0, x / reach))
        return (1 - along * along * (3 - 2 * along)) + 0.12

    shore = outline(0, reach, 22, falls, 2)
    land.shape(shape.custom([vec2(0, HORIZON + 2)] + shore + [vec2(reach + 6, HORIZON + 2)]))
    return land


COAST = coast()


# the sky, the stars and the moon. then the clouds drift over them all
@micropython.viper
def sky(pixels: ptr32, rows: ptr32, scene: ptr32, moon: ptr32, frame: int):
    y = 0
    while y < HORIZON:
        row_colour = int(rows[y])
        at = y << 7
        end = at + 128
        while at < end:
            pixels[at] = row_colour
            at += 1
        y += 1

    star = 0
    while star < STARS:
        phase = (int(scene[star * 3 + 2]) + frame * 5) & 1023
        twinkle = 30 + ((phase if phase < 512 else 1023 - phase) >> 2)
        at = (int(scene[star * 3 + 1]) << 7) | int(scene[star * 3])
        under = int(pixels[at])
        red = (under & 0xff) + twinkle
        green = ((under >> 8) & 0xff) + twinkle
        blue = ((under >> 16) & 0xff) + twinkle
        pixels[at] = OPAQUE | ((255 if blue > 255 else blue) << 16) | ((255 if green > 255 else green) << 8) | (255 if red > 255 else red)
        star += 1

    # the moon and its halo, each pixel blended in by how much it covers
    top = MOON_Y - (MOON_BOX >> 1)
    left = MOON_X - (MOON_BOX >> 1)
    y = 0
    while y < MOON_BOX:
        x = 0
        while x < MOON_BOX:
            moon_pixel = int(moon[y * MOON_BOX + x])
            alpha = (moon_pixel >> 24) & 0xff
            if alpha:
                at = ((top + y) << 7) | (left + x)
                under = int(pixels[at])
                red = (under & 0xff) + ((((moon_pixel & 0xff) - (under & 0xff)) * alpha) >> 8)
                green = ((under >> 8) & 0xff) + (((((moon_pixel >> 8) & 0xff) - ((under >> 8) & 0xff)) * alpha) >> 8)
                blue = ((under >> 16) & 0xff) + (((((moon_pixel >> 16) & 0xff) - ((under >> 16) & 0xff)) * alpha) >> 8)
                pixels[at] = OPAQUE | (blue << 16) | (green << 8) | red
            x += 1
        y += 1


# two layers of cloud drifting at different speeds, the farther fainter.
# coloured dark to silver by how near the moon they are, blended over what's
# there
@micropython.viper
def clouds(pixels: ptr32, cloud: ptr8, lit: ptr32, drift: ptr32):
    near = int(drift[0])
    far = int(drift[1])
    far_share = int(drift[2])
    dark = int(drift[3])
    bright = int(drift[4])
    dark_red = dark & 0xff
    dark_green = (dark >> 8) & 0xff
    dark_blue = (dark >> 16) & 0xff
    bright_red = bright & 0xff
    bright_green = (bright >> 8) & 0xff
    bright_blue = (bright >> 16) & 0xff
    y = 0
    while y < HORIZON:
        row = y * CLOUD_WIDTH
        far_row = ((y + FAR_ROW_OFFSET) % HORIZON) * CLOUD_WIDTH
        from_moon_y = y - MOON_Y
        x = 0
        while x < 128:
            # the cloud's colour is shared by two columns, how much cloud
            # each has is its own
            from_moon_x = x - MOON_X
            distance = (from_moon_x * from_moon_x + from_moon_y * from_moon_y) >> 7
            light = int(lit[distance if distance < 256 else 255])
            cloud_red = dark_red + (((bright_red - dark_red) * light) >> 8)
            cloud_green = dark_green + (((bright_green - dark_green) * light) >> 8)
            cloud_blue = dark_blue + (((bright_blue - dark_blue) * light) >> 8)
            column = x
            while column < x + 2:
                amount = int(cloud[row + ((column + near) & (CLOUD_WIDTH - 1))])
                # the far layer is stretched 1.5x across
                amount += (int(cloud[far_row + ((column * 3 // 2 + far) & (CLOUD_WIDTH - 1))]) * far_share) >> 8
                if amount:
                    if amount > 255:
                        amount = 255
                    at = (y << 7) | column
                    under = int(pixels[at])
                    red = (under & 0xff) + (((cloud_red - (under & 0xff)) * amount) >> 8)
                    green = ((under >> 8) & 0xff) + (((cloud_green - ((under >> 8) & 0xff)) * amount) >> 8)
                    blue = ((under >> 16) & 0xff) + (((cloud_blue - ((under >> 16) & 0xff)) * amount) >> 8)
                    pixels[at] = OPAQUE | (blue << 16) | (green << 8) | red
                column += 1
            x += 2
        y += 1


# each sea pixel reflects the sky above it as a mirror at the horizon would,
# shifted across and up by the wave slope there. so the moon breaks up into a
# glittering path. rows is SEA, see there
@micropython.viper
def sea(pixels: ptr32, rows: ptr32, sin: ptr32, travel: ptr32):
    lift = int(travel[3])
    y = 0
    while y < SEA_ROWS:
        row_at = y * SEA_STRIDE
        water = int(rows[row_at])
        reflect = int(rows[row_at + 1])
        wave0_phase = int(rows[row_at + 2]) - int(travel[0])
        wave0_step = int(rows[row_at + 3])
        wave0_across = (int(rows[row_at + 4]) * lift) >> 8
        wave0_up = (int(rows[row_at + 5]) * lift) >> 8
        wave1_phase = int(rows[row_at + 6]) - int(travel[1])
        wave1_step = int(rows[row_at + 7])
        wave1_across = (int(rows[row_at + 8]) * lift) >> 8
        wave1_up = (int(rows[row_at + 9]) * lift) >> 8
        wave2_phase = int(rows[row_at + 10]) - int(travel[2])
        wave2_step = int(rows[row_at + 11])
        wave2_across = (int(rows[row_at + 12]) * lift) >> 8
        wave2_up = (int(rows[row_at + 13]) * lift) >> 8
        water_red = water & 0xff
        water_green = (water >> 8) & 0xff
        water_blue = (water >> 16) & 0xff
        mirror = HORIZON - 1 - y
        at = (HORIZON + y) << 7
        x = 0
        while x < 128:
            # each wave's slope here, its phase a quarter turn on
            wave0_slope = int(sin[((wave0_phase >> 8) + 256) & 1023])
            wave1_slope = int(sin[((wave1_phase >> 8) + 256) & 1023])
            wave2_slope = int(sin[((wave2_phase >> 8) + 256) & 1023])
            across = x + ((wave0_slope * wave0_across + wave1_slope * wave1_across + wave2_slope * wave2_across) >> 16)
            up = mirror + ((wave0_slope * wave0_up + wave1_slope * wave1_up + wave2_slope * wave2_up) >> 16)
            if across < 0:
                across = 0
            elif across > 127:
                across = 127
            if up < 0:
                up = 0
            elif up > HORIZON - 1:
                up = HORIZON - 1
            reflected = int(pixels[(up << 7) | across])
            red = water_red + (((reflected & 0xff) * reflect) >> 8)
            green = water_green + ((((reflected >> 8) & 0xff) * reflect) >> 8)
            blue = water_blue + ((((reflected >> 16) & 0xff) * reflect) >> 8)
            if red > 255:
                red = 255
            if green > 255:
                green = 255
            if blue > 255:
                blue = 255
            pixels[at + x] = OPAQUE | (blue << 16) | (green << 8) | red
            wave0_phase += wave0_step
            wave1_phase += wave1_step
            wave2_phase += wave2_step
            x += 1
        y += 1


# per frame: each cloud layer's drift, the far layer's share x256, and the
# cloud colours
DRIFTING = array("i", [0, 0, int(FAR_LAYER * 256), pack(CLOUD_DARK), pack(CLOUD_LIT)])

# per sea row: water colour and how much it reflects x256. then per wave:
# phase at the left edge, step per px (1/1024 turn x256), shift across, shift
# up (px x256). phases are set each frame
SEA = array("i", [0] * SEA_ROWS * SEA_STRIDE)

# DISTANCE: how far out each row is. WAVE: per wave the wavenumber across, the
# wavenumber out, speed, a random start and steepness
DISTANCE = []
WAVE = []
for length, heading, steepness in WAVES:
    wavenumber = 2 * math.pi / length
    WAVE.append((wavenumber * math.cos(math.radians(heading)), wavenumber * math.sin(math.radians(heading)),
                 math.sqrt(9.8 * wavenumber), getrandbits(10) / 1024 * 2 * math.pi, steepness))
for row in range(SEA_ROWS):
    distance = FOCAL / (row + 0.5)
    DISTANCE.append(distance)
    # 0 at the horizon, 1 close by
    nearness = (row + 1) / SEA_ROWS
    SEA[row * SEA_STRIDE] = pack(mix(SEA_FAR, SEA_NEAR, nearness ** 0.7))
    SEA[row * SEA_STRIDE + 1] = int(256 * (REFLECT[1] + (REFLECT[0] - REFLECT[1]) * nearness ** 0.6))

TURN = 1024 * 256 / (2 * math.pi)


for row in range(SEA_ROWS):
    distance = DISTANCE[row]
    row_at = row * SEA_STRIDE
    for wave, (wavenumber_across, wavenumber_out, _, start_phase, steepness) in enumerate(WAVE):
        # phase at x: wavenumber_across * across + wavenumber_out * out - speed * t,
        # with across being (x - middle) * out / FOCAL. only the time part changes each frame
        per_px = wavenumber_across * distance / FOCAL
        fineness = abs(per_px) + abs(wavenumber_out * distance / SEA_ROWS)
        # waves much finer than a pixel fade from view, but their steep
        # faces still carry the glitter up toward the horizon
        shows = max(0.2, min(1.0, 1.4 - fineness / 2.5)) * steepness
        lifts = max(0.6, min(1.0, 1.4 - fineness / 2.5)) * steepness
        wavenumber_total = abs(wavenumber_across) + abs(wavenumber_out)
        SEA[row_at + 2 + wave * 4] = int((wavenumber_across * -64 * distance / FOCAL + wavenumber_out * distance + start_phase) * TURN) & 0x3ffffff
        SEA[row_at + 3 + wave * 4] = int(per_px * TURN)
        SEA[row_at + 4 + wave * 4] = int(shows * SHIFT[0] * 256 * wavenumber_across / wavenumber_total)
        SEA[row_at + 5 + wave * 4] = int(lifts * SHIFT[1] * 256 * wavenumber_out / wavenumber_total)

# how far each wave has travelled, in the same units as its phase, and how
# much steeper sound makes them all, x256
TRAVEL = array("i", [0, 0, 0, 256])


start = last = time.ticks_ms()
frame = 0
loud = 0.0


def update():
    global last, frame, loud

    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, last) / 1000
    last = now
    seconds = time.ticks_diff(now, start) / 1000
    frame += 1

    if mic.active():
        loud += (mic.level() - loud) * (1 - math.exp(-2 * elapsed))
    else:
        loud += (0 - loud) * (1 - math.exp(-elapsed))

    DRIFTING[0] = int(seconds * DRIFT[0])
    DRIFTING[1] = int(seconds * DRIFT[1])

    for wave in range(3):
        TRAVEL[wave] = int(WAVE[wave][2] * seconds * TURN) & 0x3ffffff
    TRAVEL[3] = int(256 * (1 + loud * LOUD_WAVES))

    # the coast before the sea, so it shows in the water too
    pixels = memoryview(screen)
    sky(pixels, SKY, SCENE, MOON_TEXTURE, frame)
    clouds(pixels, CLOUDS, LIT, DRIFTING)
    screen.blit(COAST, vec2(0, 0))
    sea(pixels, SEA, SIN, TRAVEL)

    screen.bloom(*BLOOM)
