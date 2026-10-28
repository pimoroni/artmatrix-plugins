import math
import time
import micropython
from array import array
from micropython import const
from random import getrandbits

from plugin_config import plugin_config

# per curtain: colour at its edge, part way up and at the top of its glow.
# then the sky at the top and at the horizon
SCHEMES = {
    "boreal": [[[(90, 255, 160), (60, 200, 170), (140, 60, 200)],
                [(90, 255, 150), (220, 70, 150), (120, 40, 170)],
                [(80, 240, 180), (50, 160, 190), (60, 60, 170)]],
               (3, 4, 22), (16, 34, 72)],
    "solar": [[[(255, 110, 160), (200, 60, 200), (90, 40, 180)],
               [(255, 150, 120), (230, 70, 140), (120, 30, 150)],
               [(220, 90, 220), (140, 60, 220), (60, 40, 160)]],
              (6, 2, 18), (40, 20, 60)],
    "glacier": [[[(140, 240, 255), (70, 150, 255), (110, 80, 220)],
                 [(120, 255, 220), (60, 190, 230), (90, 70, 210)],
                 [(170, 220, 255), (100, 120, 240), (80, 50, 190)]],
                (2, 4, 18), (14, 30, 66)],
}

cfg = plugin_config("aurora", {
    "scheme": "boreal",  # one of SCHEMES
    "listen": 1,  # 1 to react to sound, 0 to ignore it
})
scheme = cfg["scheme"]
listen = cfg["listen"]

# unknown names fall back to the default so the config page ticks what's showing
if scheme not in SCHEMES:
    scheme = "boreal"
COLOURS, SKY_TOP, SKY_HORIZON = SCHEMES[scheme]

hearing = mic if listen else None

CURTAINS = const(3)

# a viper pixel's alpha byte, fully opaque
OPAQUE = const(-16777216)

# a curtain's glow runs from BELOW px under its edge to ABOVE px over it, in
# 1/4 px steps
BELOW = const(6)
ABOVE = const(70)
GLOW = const((BELOW + ABOVE) * 4)


# per curtain: how far down its edge sits in px, how far it waves, how bright
# it is and how fast it drifts
CURTAIN = [(100, 12, 0.8, 1.0), (78, 10, 0.65, -0.7), (58, 8, 0.45, 0.45)]

# how fast everything moves, 1 as designed
PACE = 2

# glow around the light: bloom(threshold, intensity, radius, strength)
BLOOM = (24, 255, 6, 1.6)

# how much the bass can brighten the curtains, and how far a kick's pulse
# runs along them, in px a second
BASS_LIFT = 0.6
PULSE_SPEED = 90

# a kick's swell: half its width in columns, and how much it brightens at its
# middle, out of 256
PULSE_WIDTH = const(20)
PULSE_GAIN = const(150)

# where the pulse is when there isn't one. a real pulse starts left of the
# panel at -PULSE_WIDTH, so this sits well past that
NO_PULSE = const(-1000)

# stars, and the trees: this many spruces, taller toward the sides
STARS = const(110)
TREES = 26

# points along each curtain's ribbon, two a column
RIBBON_POINTS = const(256)

# sine table: 1024 steps a turn, values x256
SIN = array("i", [int(math.sin(i * 2 * math.pi / 1024) * 256) for i in range(1024)])

# per curtain and column, filled each frame. EDGES: the edge in 1/4 px from
# the top. RAYS: brightness (0-256 and up) in the low 16 bits, squash in the
# high (256 as drawn, more is shorter)
EDGES = array("i", [0] * CURTAINS * 128)
RAYS = array("i", [0] * CURTAINS * 128)

# per curtain: edge height, sway and brightness x256. then the phases of its
# folds, rays, patches and ray heights. then how far it folds in 1/256 px
WAVE_SLOTS = const(12)
WAVES = array("i", [0] * CURTAINS * WAVE_SLOTS)

# room for shape() to add up each column's ribbon, edge and spread ribbon
LAID = array("i", [0] * 384)

# how far the ribbon sways back and forth, in px: past about 20 it folds
FOLD = 14


def pack(rgb):
    return 0xff000000 | (int(rgb[2]) << 16) | (int(rgb[1]) << 8) | int(rgb[0])


# each curtain's colour and strength from below its edge to the top of its
# glow, per 1/4 px: a soft lower edge, a long fade upward
GLOWS = array("I", [0] * CURTAINS * GLOW)
for curtain in range(CURTAINS):
    stops = COLOURS[curtain]
    for i in range(GLOW):
        # px above the edge, and how far up the glow that is, 0 to 1
        above = i / 4 - BELOW
        if above < 0:
            strength = math.exp(above / 2.5)
            up = 0
        else:
            strength = math.exp(-above / 30) * (0.7 + 0.3 * math.exp(-above / 6))
            up = min(1, above / ABOVE)
        if up < 0.18:
            blend = up / 0.18
            from_colour, to_colour = stops[0], stops[1]
        else:
            blend = min(1, (up - 0.18) / 0.5)
            from_colour, to_colour = stops[1], stops[2]
        mixed = [from_colour[channel] + (to_colour[channel] - from_colour[channel]) * blend for channel in range(3)]
        GLOWS[curtain * GLOW + i] = pack([min(255, value * strength) for value in mixed])

# a deep blue sky, lighter toward the horizon
SKY = array("I", [pack([SKY_TOP[channel] + (SKY_HORIZON[channel] - SKY_TOP[channel]) * (y / 127) ** 1.6
                        for channel in range(3)]) for y in range(128)])

# stars: x, y and twinkle phase each
SCENE = array("i", [0] * STARS * 3)
for star in range(STARS):
    SCENE[star * 3] = getrandbits(7)
    SCENE[star * 3 + 1] = getrandbits(7)
    SCENE[star * 3 + 2] = getrandbits(10)


# the ground and spruces along it, taller toward the sides. drawn once,
# antialiased, on a clear background to lay over the sky
def forest():
    trees = image(128, 128)  # noqa: F821
    trees.antialias = image.X4  # noqa: F821
    trees.pen = color.rgb(0, 0, 0, 0)  # noqa: F821
    trees.clear()
    trees.pen = color.black  # noqa: F821

    # the ground, gently uneven
    ground = [vec2(0, 128), vec2(0, 125)]  # noqa: F821
    for x in range(8, 129, 8):
        ground.append(vec2(x, 124 + getrandbits(2) * 0.6))  # noqa: F821
    ground.append(vec2(128, 128))  # noqa: F821
    trees.shape(shape.custom(ground))  # noqa: F821

    for _ in range(TREES):
        tree_x = getrandbits(7)
        side = abs(tree_x - 64) / 64
        height = 10 + 70 * side ** 2.2 + getrandbits(4)
        half = max(2, height / 5)
        top = 126 - height

        # a spruce: a point at the top, then down each side in ragged tiers,
        # each tier reaching out and tucking back in
        tiers = max(3, int(height / 6))
        right = [vec2(tree_x, top)]  # noqa: F821
        for tier in range(1, tiers + 1):
            down = tier / tiers
            y = top + height * down
            reach = half * down * (0.85 + getrandbits(3) / 40)
            right.append(vec2(tree_x + reach, y - height / tiers * 0.25))  # noqa: F821
            if tier < tiers:
                right.append(vec2(tree_x + reach * 0.55, y))  # noqa: F821
        left = []
        for point in reversed(right[1:]):
            mirrored = tree_x - (point.x - tree_x)
            left.append(vec2(mirrored, point.y))  # noqa: F821
        trunk = [vec2(tree_x + half * 0.15, 127), vec2(tree_x - half * 0.15, 127)]  # noqa: F821
        trees.shape(shape.custom(right + trunk + left))  # noqa: F821

    return trees


FOREST = forest()


# each curtain is a ribbon seen side on, its points swaying on slow waves.
# a column's brightness is how much ribbon lands in it. even columns only,
# as paint() draws two at a time
@micropython.viper
def shape(edges: ptr32, rays: ptr32, waves: ptr32, sin: ptr32,  # noqa: F821
          pulse: int, work: ptr32):  # noqa: F821
    curtain = 0
    while curtain < CURTAINS:
        slot = curtain * WAVE_SLOTS
        base = int(waves[slot])
        sway = int(waves[slot + 1])
        bright = int(waves[slot + 2])
        ribbon_phase1 = int(waves[slot + 3])
        ribbon_phase2 = int(waves[slot + 4])
        shimmer_phase1 = int(waves[slot + 5])
        shimmer_phase2 = int(waves[slot + 6])
        patch_phase1 = int(waves[slot + 7])
        patch_phase2 = int(waves[slot + 8])
        height_phase1 = int(waves[slot + 9])
        height_phase2 = int(waves[slot + 10])
        fold = int(waves[slot + 11])

        x = 0
        while x < 384:
            work[x] = 0
            x += 1

        # lay the ribbon over the columns. along is in 1/256 px
        point = 0
        while point < RIBBON_POINTS:
            folding = ((int(sin[(ribbon_phase1 + point * 5) & 1023]) * fold) >> 8) + ((int(sin[(ribbon_phase2 - point * 13) & 1023]) * fold) >> 9)
            along = point * 128 + folding
            x = along >> 8
            swaying = ((int(sin[(ribbon_phase2 + point * 4) & 1023]) * sway) >> 8) + ((int(sin[(ribbon_phase1 + point * 11) & 1023]) * sway) >> 9)
            edge = base + swaying
            if 0 <= x < 128:
                work[x] = int(work[x]) + 1
                work[128 + x] = int(work[128 + x]) + edge
            point += 1

        # spread each column's ribbon and edge over its neighbours, so bunched
        # ribbon is a soft glow and not a bright line
        x = 0
        while x < 128:
            weight = 0
            edge_sum = 0
            offset = -3
            while offset <= 3:
                at = x + offset
                if 0 <= at < 128:
                    near = 4 - (offset if offset > 0 else -offset)
                    weight += int(work[at]) * near
                    edge_sum += int(work[128 + at]) * near
                offset += 1
            if weight:
                edges[curtain * 128 + x] = edge_sum // weight
            # 2 points a column is the ribbon unbunched, 256 here
            work[256 + x] = weight * 8
            x += 2

        x = 0
        while x < 128:
            # from half as bright where stretched, rising more and more gently
            # where bunched, so there's no hard edge to it
            laid = int(work[256 + x])
            laid = 128 + (laid >> 1)
            if laid > 256:
                laid = 256 + (laid - 256) * 128 // (laid - 128)

            # a gentle, broad shimmer along the curtain
            light = 190 + (int(sin[(shimmer_phase1 + x * 9) & 1023]) >> 3) + (int(sin[(shimmer_phase2 - x * 15) & 1023]) >> 4)
            light = (light * laid) >> 8

            # patches: a slow broad pattern that can fade a stretch to nothing
            patch = 140 + (int(sin[(patch_phase1 + x * 6) & 1023]) >> 1) + (int(sin[(patch_phase2 - x * 14) & 1023]) >> 2)
            if patch < 0:
                patch = 0
            patch = (patch * patch) >> 8
            light = (light * patch) >> 8

            # a kick's pulse, a soft swell of light moving along the curtain
            if pulse != NO_PULSE:
                distance = x - pulse
                if distance < 0:
                    distance = -distance
                if distance < PULSE_WIDTH:
                    swell = 128 + (int(sin[(distance * 512 // PULSE_WIDTH + 256) & 1023]) >> 1)
                    light = (light * (256 + ((swell * PULSE_GAIN) >> 8))) >> 8
            light = (light * bright) >> 8
            if light < 0:
                light = 0
            elif light > 0xffff:
                light = 0xffff

            # how tall this column's rays reach: more squash is shorter
            squash = 300 + ((int(sin[(height_phase1 + x * 11) & 1023]) * 70) >> 8) + ((int(sin[(height_phase2 - x * 19) & 1023]) * 30) >> 8)
            rays[curtain * 128 + x] = light | (squash << 16)
            x += 2
        curtain += 1


# two columns at a time, as the curtains are soft. each row is the sky plus
# every curtain's glow at its distance below that curtain's edge. rows no
# curtain reaches are just sky. then the stars
@micropython.viper
def paint(edges: ptr32, rays: ptr32, glows: ptr32, sky: ptr32,  # noqa: F821
          scene: ptr32, pixels: ptr32, frame: int):  # noqa: F821
    x = 0
    while x < 128:
        # each curtain's edge, brightness and squash in this column. then the
        # rows between them that any glow reaches
        front_edge = int(edges[x]) + BELOW * 4
        middle_edge = int(edges[128 + x]) + BELOW * 4
        back_edge = int(edges[256 + x]) + BELOW * 4
        front_packed = int(rays[x])
        middle_packed = int(rays[128 + x])
        back_packed = int(rays[256 + x])
        front_light = front_packed & 0xffff
        middle_light = middle_packed & 0xffff
        back_light = back_packed & 0xffff
        front_squash = front_packed >> 16
        middle_squash = middle_packed >> 16
        back_squash = back_packed >> 16
        top = 127
        bottom = 0
        curtain = 0
        while curtain < CURTAINS:
            edge = front_edge if curtain == 0 else (middle_edge if curtain == 1 else back_edge)
            squash = front_squash if curtain == 0 else (middle_squash if curtain == 1 else back_squash)
            reach = BELOW * 4 + ((GLOW - BELOW * 4) << 8) // squash
            glow_top = (edge - reach + 3) >> 2
            glow_bottom = edge >> 2
            if glow_top < top:
                top = glow_top
            if glow_bottom > bottom:
                bottom = glow_bottom
            curtain += 1
        if top < 0:
            top = 0
        if bottom > 127:
            bottom = 127

        y = 0
        while y < 128:
            colour = int(sky[y])
            if top <= y <= bottom:
                red = colour & 0xff
                green = (colour >> 8) & 0xff
                blue = (colour >> 16) & 0xff
                curtain = 0
                while curtain < CURTAINS:
                    if curtain == 0:
                        distance = front_edge - y * 4
                        squash = front_squash
                        light = front_light
                    elif curtain == 1:
                        distance = middle_edge - y * 4
                        squash = middle_squash
                        light = middle_light
                    else:
                        distance = back_edge - y * 4
                        squash = back_squash
                        light = back_light
                    if light and distance >= 0:
                        if distance > BELOW * 4:
                            distance = BELOW * 4 + (((distance - BELOW * 4) * squash) >> 8)
                        if distance < GLOW:
                            glow = int(glows[curtain * GLOW + distance])
                            red += ((glow & 0xff) * light) >> 8
                            green += (((glow >> 8) & 0xff) * light) >> 8
                            blue += (((glow >> 16) & 0xff) * light) >> 8
                    curtain += 1
                if red > 255:
                    red = 255
                if green > 255:
                    green = 255
                if blue > 255:
                    blue = 255
                colour = OPAQUE | (blue << 16) | (green << 8) | red
            at = (y << 7) | x
            pixels[at] = colour
            pixels[at + 1] = colour
            y += 1
        x += 2

    star = 0
    while star < STARS:
        star_x = int(scene[star * 3])
        star_y = int(scene[star * 3 + 1])
        # a slow triangle wave, from each star's own phase
        phase = (int(scene[star * 3 + 2]) + frame * 7) & 1023
        twinkle = 40 + ((phase if phase < 512 else 1023 - phase) >> 2)
        at = (star_y << 7) | star_x
        pixel = int(pixels[at])
        red = (pixel & 0xff) + twinkle
        green = ((pixel >> 8) & 0xff) + twinkle
        blue = ((pixel >> 16) & 0xff) + twinkle
        if red > 255:
            red = 255
        if green > 255:
            green = 255
        if blue > 255:
            blue = 255
        pixels[at] = OPAQUE | (blue << 16) | (green << 8) | red
        star += 1


start = last = time.ticks_ms()
frame = 0
bass = 0.0
pulse_at = None


def update():
    global last, frame, bass, pulse_at

    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, last) / 1000
    last = now
    seconds = time.ticks_diff(now, start) / 1000 * PACE
    frame += 1

    if hearing is not None and hearing.active():
        bands = hearing.spectrum()
        target = (bands[0] + bands[1] + bands[2] + bands[3]) / 4
        bass += (target - bass) * (1 - math.exp(-1.5 * elapsed))
        if hearing.kick() and pulse_at is None:
            pulse_at = seconds
    else:
        bass += (0 - bass) * (1 - math.exp(-0.5 * elapsed))

    pulse = NO_PULSE
    if pulse_at is not None:
        pulse = int((seconds - pulse_at) * PULSE_SPEED) - PULSE_WIDTH
        if pulse > 128 + PULSE_WIDTH:
            pulse_at = None
            pulse = NO_PULSE

    for curtain, (height, sway, bright, drift) in enumerate(CURTAIN):
        slot = curtain * WAVE_SLOTS
        # the whole curtain rises and falls over about half a minute. it also
        # comes and goes, at times all but vanishing
        WAVES[slot] = int((height + 6 * math.sin(seconds * 0.11 + curtain * 2.1)) * 4)
        WAVES[slot + 1] = sway * 4
        presence = 0.5 + 0.5 * math.sin(seconds * 0.071 + curtain * 2.3) * math.cos(seconds * 0.043 + curtain)
        WAVES[slot + 2] = int(256 * bright * (0.15 + 0.95 * presence * presence + bass * BASS_LIFT))
        WAVES[slot + 3] = int(seconds * 23 * drift) + curtain * 300
        WAVES[slot + 4] = int(-seconds * 17 * drift) + curtain * 170
        # the rays drift slowly along the curtain
        WAVES[slot + 5] = int(seconds * 17 * drift) + curtain * 1000
        WAVES[slot + 6] = int(-seconds * 11) + curtain * 2000
        WAVES[slot + 7] = int(seconds * 9 * drift) + curtain * 500
        WAVES[slot + 8] = int(-seconds * 13) + curtain * 250
        WAVES[slot + 9] = int(seconds * 7 * drift) + curtain * 333
        WAVES[slot + 10] = int(-seconds * 11) + curtain * 600
        WAVES[slot + 11] = int(FOLD * 256 * (0.7 + 0.3 * math.sin(seconds * 0.05 + curtain * 1.7)))

    shape(EDGES, RAYS, WAVES, SIN, pulse, LAID)
    paint(EDGES, RAYS, GLOWS, SKY, SCENE, memoryview(screen), frame)
    screen.blit(FOREST, vec2(0, 0))  # noqa: F821
    screen.bloom(*BLOOM)  # noqa: F821
