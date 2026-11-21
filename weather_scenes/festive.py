# the days of the year that dress the weather scenes up. __init__ puts the day's theme in
# w["theme"], and calls behind() once the sky is drawn and front() once the tree is.
# scenery.py swaps the tree and calls dress() here whenever it redraws the land.
#
# christmas: the tree is a fir hung with lights that twinkle, a star on top and presents
# round its foot. on the beach the lights wind up the palm.
# halloween: a bare dark tree, pumpkins with candles in, and bats.
# bonfire: a bonfire burning in the meadow, and fireworks once it's dark.
# newyear: more fireworks, and the year written across the top of the sky.
#
# the weather itself is left alone: it still only snows when it's snowing
import math
import micropython
from array import array
from random import getrandbits, randint, uniform

# loaded by path, as __init__ loads them and this
HERE = __name__.rsplit("/", 1)[0]
sky = __import__(HERE + "/sky")
scenery = __import__(HERE + "/scenery")

# a pixel's alpha byte fully on, written signed for viper
OPAQUE = const(-16777216)

# fireworks start once the daylight is below this
DARK = 0.35


def pack(rgb):
    return (int(rgb[2]) << 16) | (int(rgb[1]) << 8) | int(rgb[0])


# --- sparks: fireworks and flames ---

# per spark: x and y in 1/64 px, speed across and down in 1/64 px a second, ms it has left,
# ms it started with and its colour
PART = const(7)
ROCKETS = const(200)
FLAMES = const(60)
# per set of sparks: how many, ms since the last frame, gravity in 1/64 px a second each
# second, 1 for a fire, which starts each spark again when it burns out, and a seed. then
# for a firework, how many sparks to burst now, where from in 1/64 px, their two colours,
# the next spark to use and their most speed in 1/64 px a second. for a fire, the middle
# of its foot in 1/64 px, its two main colours, half its width in 1/64 px and its third
BURST = const(5)
ROCKET_STATE = array("i", [ROCKETS, 0, 26 * 64, 0, getrandbits(30), 0, 0, 0, 0, 0, 0, 0, 0, 0])
FLAME_STATE = array("i", [FLAMES, 0, 0, 1, getrandbits(30), 0, 0, 0, pack((255, 96, 20)), pack((255, 160, 34)), 0, 0,
                          6 * 64, pack((255, 216, 90))])
ROCKET_PARTS = array("i", [0] * (ROCKETS * PART))
FLAME_PARTS = array("i", [0] * (FLAMES * PART))

# a firework's two colours
FIREWORKS = (((255, 80, 60), (255, 190, 120)), ((255, 210, 70), (255, 250, 200)), ((90, 170, 255), (210, 230, 255)),
             ((90, 240, 120), (220, 255, 180)), ((255, 110, 220), (255, 200, 240)), ((200, 130, 255), (255, 255, 255)),
             ((255, 150, 40), (255, 230, 120)))
# seconds between them, and sparks in each, on bonfire night and at new year
SHOWS = {"bonfire": ((0.6, 2.2), (34, 48)), "newyear": ((0.25, 1.1), (40, 56))}


# moves the sparks on and adds each one's light to the screen, fading as it burns out.
# a firework's sparks leave a short trail, a fire's are fatter while they're young
@micropython.viper
def sparks(pixels: ptr32, parts: ptr32, state: ptr32, sine: ptr32):  # noqa: F821
    count = state[0]
    step = state[1]
    gravity = state[2]
    fire = state[3]
    seed = state[4]
    burst = state[BURST]
    at = state[10]
    while burst > 0:
        spot = at * PART
        at += 1
        if at >= count:
            at = 0
        seed = seed * 1664525 + 1013904223
        angle = (seed >> 8) & 255
        speed = (state[11] * (90 + ((seed >> 17) & 127) + ((seed >> 24) & 31))) >> 8
        parts[spot] = state[6]
        parts[spot + 1] = state[7]
        parts[spot + 2] = (speed * sine[angle]) >> 8
        parts[spot + 3] = (speed * sine[(angle + 64) & 255]) >> 8
        life = 750 + ((seed >> 4) & 511)
        parts[spot + 4] = life
        parts[spot + 5] = life
        parts[spot + 6] = state[9] if (seed >> 29) & 1 else state[8]
        burst -= 1
    if fire == 0:
        state[BURST] = 0
        state[10] = at

    n = 0
    while n < count:
        spot = n * PART
        n += 1
        life = parts[spot + 4] - step
        if life <= 0:
            if fire == 0:
                parts[spot + 4] = 0
                continue
            # a new flame, taller the nearer the middle it starts. now and then a spark
            # that flies higher
            seed = seed * 1664525 + 1013904223
            off = ((seed >> 8) & 255) - 128
            parts[spot] = state[6] + ((off * state[12]) >> 7)
            parts[spot + 1] = state[7] - ((seed >> 18) & 127)
            parts[spot + 2] = 0 - off * 3
            parts[spot + 3] = 0 - (1500 + ((seed >> 20) & 1023))
            life = 260 + (128 - (off if off > 0 else 0 - off)) * 4 + ((seed >> 14) & 127)
            pick = (seed >> 26) & 3
            parts[spot + 6] = state[13] if pick == 0 else state[9] if pick == 1 else state[8]
            if ((seed >> 4) & 15) == 0:
                life = 1500
                parts[spot + 2] = off * 6
                parts[spot + 3] = -3400
                parts[spot + 6] = state[13]
            parts[spot + 5] = life
        parts[spot + 4] = life
        across = parts[spot + 2]
        down = parts[spot + 3] + (gravity * step) // 1000
        if fire == 0:
            across -= (across * step) >> 10
            down -= (down * step) >> 10
        x = parts[spot] + (across * step) // 1000
        y = parts[spot + 1] + (down * step) // 1000
        parts[spot] = x
        parts[spot + 1] = y
        parts[spot + 2] = across
        parts[spot + 3] = down
        # full strength for the first third of its life, then fading
        strength = (life * 384) // parts[spot + 5]
        if strength > 256:
            strength = 256
        colour = parts[spot + 6]
        dab = 0
        while dab < 2:
            if dab:
                # the second dab: a firework's trail, or a flame's other half
                strength >>= 1
                if fire:
                    if strength < 60:
                        break
                    x += 64
                else:
                    x -= across >> 5
                    y -= down >> 5
            column = x >> 6
            row = y >> 6
            if 0 <= row < 128 and 0 <= column < 128:
                here = (row << 7) | column
                under = pixels[here]
                red = (under & 0xff) + (((colour & 0xff) * strength) >> 8)
                green = ((under >> 8) & 0xff) + ((((colour >> 8) & 0xff) * strength) >> 8)
                blue = ((under >> 16) & 0xff) + ((((colour >> 16) & 0xff) * strength) >> 8)
                pixels[here] = OPAQUE | ((255 if blue > 255 else blue) << 16) | ((255 if green > 255 else green) << 8) | (255 if red > 255 else red)
            dab += 1
    state[4] = seed


# --- the lights on the tree ---

# per light: the two nodes of the tree it hangs between and how far along x256, how far
# across and down from there in 1/16 px, its colour and where it is in its twinkle
LIGHT = const(7)
MOST_LIGHTS = const(40)
LIGHTS = array("i", [0] * (MOST_LIGHTS * LIGHT))
# how many, the twinkle's clock and how strong their glow is, 0 to 256
LIGHT_STATE = array("i", [0, 0, 0])
LIGHT_COLOURS = ((255, 50, 40), (255, 200, 40), (70, 150, 255), (70, 235, 100), (255, 90, 200))


# each light where the tree has swayed to, brightening and dimming, with a glow round it
# after dark
@micropython.viper
def twinkle(pixels: ptr32, at: ptr32, lights: ptr32, state: ptr32):  # noqa: F821
    clock = state[1]
    glow = state[2]
    n = 0
    finish = state[0] * LIGHT
    while n < finish:
        first = lights[n] * 3
        second = lights[n + 1] * 3
        share = lights[n + 2]
        column = (at[first] + (((at[second] - at[first]) * share) >> 8) + lights[n + 3]) >> 4
        row = (at[first + 1] + (((at[second + 1] - at[first + 1]) * share) >> 8) + lights[n + 4]) >> 4
        colour = lights[n + 5]
        phase = (lights[n + 6] + clock) & 255
        bright = 132 + (phase if phase < 128 else 255 - phase)
        if 1 <= row < 127 and 1 <= column < 127:
            here = (row << 7) | column
            red = ((colour & 0xff) * bright) >> 8
            green = (((colour >> 8) & 0xff) * bright) >> 8
            blue = (((colour >> 16) & 0xff) * bright) >> 8
            pixels[here] = OPAQUE | (blue << 16) | (green << 8) | red
            if glow:
                strength = (glow * bright) >> 10
                red = (red * strength) >> 8
                green = (green * strength) >> 8
                blue = (blue * strength) >> 8
                side = 0
                while side < 4:
                    spot = here + (1 if side == 0 else -1 if side == 1 else 128 if side == 2 else -128)
                    under = pixels[spot]
                    r = (under & 0xff) + red
                    g = ((under >> 8) & 0xff) + green
                    b = ((under >> 16) & 0xff) + blue
                    pixels[spot] = OPAQUE | ((255 if b > 255 else b) << 16) | ((255 if g > 255 else g) << 8) | (255 if r > 255 else r)
                    side += 1
        n += LIGHT


# hangs the lights on the tree standing now: in swags from bough to bough of the fir, or
# winding up the palm
def hang():
    names = scenery.nodes_at
    lights = []
    if scenery.standing is scenery.fir:
        for tier, count in enumerate((6, 5, 4, 3, 2)):
            for light in range(count):
                share = (light + 0.5) / count
                lights.append(("left%d" % tier, "right%d" % tier, share, 0, 1.5 + 2.4 * math.sin(math.pi * share)))
    elif scenery.standing is scenery.palm:
        for bone in range(6):
            for light in range(2):
                lights.append(("t%d" % bone if bone else "base", "t%d" % (bone + 1), 0.25 + 0.5 * light, 1.6 if light else -1.6, 0))
    for at, (first, second, share, across, down) in enumerate(lights):
        spot = at * LIGHT
        LIGHTS[spot] = names[first]
        LIGHTS[spot + 1] = names[second]
        LIGHTS[spot + 2] = int(share * 256)
        LIGHTS[spot + 3] = int(across * 16)
        LIGHTS[spot + 4] = int(down * 16)
        LIGHTS[spot + 5] = pack(LIGHT_COLOURS[(at * 3 + at // 5) % len(LIGHT_COLOURS)])
        LIGHTS[spot + 6] = getrandbits(8)
    LIGHT_STATE[0] = len(lights)


# --- what's drawn onto the land ---

# presents: across and down from the tree's foot to their bottom left, width, height,
# paper and ribbon
PRESENTS = ((-20, 3, 8, 7, (206, 44, 44), (250, 214, 90)), (-11, 4, 6, 5, (52, 110, 214), (240, 244, 250)),
            (6, 4, 7, 6, (226, 170, 40), (226, 52, 52)), (14, 3, 6, 8, (150, 76, 200), (250, 214, 90)))
# pumpkins: x, y and half their width
PUMPKINS = ((22, 112, 5), (47, 113, 6), (77, 122, 5))
PUMPKIN = ((236, 120, 26), (178, 76, 18), (80, 104, 44))
# a candle's light through a pumpkin's face, and the face with the candle out
CANDLE = (255, 200, 70)
CARVED = (58, 28, 8)
LANTERN = (214, 96, 22)
# the bonfire's foot, its logs as lines from there, and the light it throws on the ground
BONFIRE = (40, 113)
LOGS = ((-9, 0, 1, -12), (9, 0, -1, -12), (-5, 1, 3, -11), (5, 1, -3, -11), (0, 1, 0, -10))
LOG = ((70, 46, 30), (112, 78, 48))
EMBERS = (255, 130, 40)


# each present as front() draws it: x, y, width, height, and pens for its paper, its
# shaded foot and its ribbon
wrapped = []


# scenery calls this once it has drawn the land, for the day's things that stay put
def dress(w, kind):
    theme = w.get("theme")
    land = scenery.LAND
    tint = scenery.tint
    pen = scenery.pen
    if theme == "christmas":
        # the presents go in front of the tree, so front() draws them. here, their
        # colours in this light
        foot = (min(scenery.PALM_AT[0], 100), scenery.PALM_AT[1] - 2) if kind == "beach" else scenery.TREE_AT
        wrapped.clear()
        for across, down, width, height, paper, ribbon in PRESENTS:
            wrapped.append((foot[0] + across, foot[1] + down - height, width, height, pen(tint(paper, 0.8)),
                            pen(tint(scenery.mix(paper, (0, 0, 0), 0.35), 0.4)), pen(tint(ribbon, 1))))
    elif theme == "halloween":
        flesh, rib, stalk = PUMPKIN
        for x, y, half in PUMPKINS:
            land.pen = pen(tint(rib, 0.4))
            land.shape(scenery.ellipse(x, y, half, half * 0.8))
            land.pen = pen(tint(flesh, 0.9))
            land.shape(scenery.ellipse(x - 0.4, y - 0.4, half - 0.9, half * 0.8 - 0.8))
            land.pen = pen(tint(rib, 0.6), 150)
            land.shape(scenery.ellipse(x, y, half * 0.45, half * 0.8 - 0.6))
            land.pen = pen(tint(flesh, 1))
            land.shape(scenery.ellipse(x, y - 0.3, half * 0.28, half * 0.8 - 1.2))
            land.pen = pen(tint(stalk, 0.6))
            land.rectangle(x, int(y - half * 0.8 - 1), 1, 2)
            # after dark the candle lights it from inside
            night = 1 - sky.clamp(w["day"])
            if night > 0.1:
                land.pen = pen(LANTERN, int(150 * night))
                land.shape(scenery.ellipse(x, y, half - 1, half * 0.8 - 1))
    elif theme == "bonfire":
        x, y = BONFIRE
        night = 1 - sky.clamp(w["day"])
        if night > 0.1:
            land.pen = brush.gradient(brush.RADIAL, x, y, x + 24, y, ((0.0, pen(EMBERS, int(120 * night))), (1.0, pen(EMBERS, 0))))
            land.shape(scenery.ellipse(x, y + 1, 24, 7))
        for at, (from_x, from_y, to_x, to_y) in enumerate(LOGS):
            land.pen = pen(tint(LOG[at % 2], 0.6))
            land.shape(shape.line(x + from_x, y + from_y, x + to_x, y + to_y, 1.9))


scenery.DRESS = dress


# --- bats ---

# each bat: how far across it is in px, how fast it flies in px a second, the row it
# flies along, where it is in its bob and in its flap
BATS = [[uniform(0, 128), uniform(14, 26) * (1 if bat % 2 else -1), 12 + bat * 9 + uniform(0, 4), uniform(0, 6.28), uniform(0, 6.28)]
        for bat in range(4)]
BAT_DAY = (24, 18, 34)
BAT_NIGHT = (84, 70, 118)


def bats(w, step):
    screen.pen = sky.pen(sky.mix(BAT_NIGHT, BAT_DAY, sky.clamp(w["day"])))
    for bat in BATS:
        bat[0] = (bat[0] + bat[1] * step + 12) % 152 - 12
        bat[3] = (bat[3] + 2.3 * step) % 6.2832
        bat[4] = (bat[4] + 15 * step) % 6.2832
        x = int(bat[0])
        y = int(bat[2] + 3.5 * math.sin(bat[3]))
        # wings up, then down
        lift = -1 if bat[4] < 3.1416 else 1
        screen.rectangle(x, y, 2, 2)
        screen.rectangle(x - 2, y + lift, 2, 1)
        screen.rectangle(x + 2, y + lift, 2, 1)
        screen.rectangle(x - 3, y + lift * 2, 1, 1)
        screen.rectangle(x + 4, y + lift * 2, 1, 1)


# --- each frame ---

# the theme and land the lights and fire were last set up for
hung = None
# seconds to the next firework, the twinkle's clock and the candles' flicker
next_burst = 0.0
twinkled = 0.0
flickered = 0.0
# the year as last measured: the text and how wide it is
year_label = None
year_width = 0
YEAR_PEN = color.rgb(255, 216, 96)
YEAR_SHADE = color.rgb(40, 24, 60, 170)


def fireworks(w, theme):
    global next_burst
    step = sky.dt
    if sky.clamp(w["day"]) < DARK:
        next_burst -= step
        if next_burst <= 0:
            gaps, sizes = SHOWS[theme]
            next_burst = uniform(*gaps)
            colours = FIREWORKS[randint(0, len(FIREWORKS) - 1)]
            ROCKET_STATE[BURST] = randint(*sizes)
            ROCKET_STATE[6] = randint(12, 116) << 6
            ROCKET_STATE[7] = randint(8, 42) << 6
            ROCKET_STATE[8] = pack(colours[0])
            ROCKET_STATE[9] = pack(colours[1])
            ROCKET_STATE[11] = randint(38, 56) << 6
    # the sparks already up burn out whatever the light does
    ROCKET_STATE[1] = int(step * 1000)
    sparks(memoryview(screen), ROCKET_PARTS, ROCKET_STATE, sky.SINE)


# after the sky and its clouds, before the land: what's up in the sky
def behind(w, t):  # noqa: ARG001
    global year_label, year_width
    theme = w.get("theme")
    if theme in SHOWS:
        fireworks(w, theme)
    if theme == "newyear" and w.get("year"):
        screen.font = font.smart
        label = str(w["year"])
        if label != year_label:
            year_label = label
            year_width = screen.measure_text(label, 1)[0]
        x = round((128 - year_width) / 2)
        screen.pen = YEAR_SHADE
        screen.text(label, vec2(x + 1, 3), 1)
        screen.pen = YEAR_PEN
        screen.text(label, vec2(x, 2), 1)


# after the tree, before the grass in front of it: the lights, the fire, the candles and
# the bats
def front(w, t):  # noqa: ARG001
    global hung, twinkled, flickered
    theme = w.get("theme")
    step = sky.dt
    pixels = memoryview(screen)
    if theme == "christmas":
        if hung != scenery.drawn:
            hung = scenery.drawn
            hang()
        twinkled = (twinkled + 150 * step) % 256
        LIGHT_STATE[1] = int(twinkled)
        # they glow a little by day too, or they'd be lost in the green
        LIGHT_STATE[2] = int(110 + 146 * (1 - sky.clamp(w["day"])))
        twinkle(pixels, scenery.AT, LIGHTS, LIGHT_STATE)
        if scenery.standing is scenery.fir:
            # the star on top, where the tip has swayed to
            tip = scenery.nodes_at["top4"] * 3
            x = scenery.AT[tip] >> 4
            y = (scenery.AT[tip + 1] >> 4) - 1
            screen.pen = color.rgb(255, 214, 70)
            screen.rectangle(x - 2, y, 5, 1)
            screen.rectangle(x, y - 2, 1, 5)
            screen.rectangle(x - 1, y - 1, 3, 3)
            screen.pen = color.rgb(255, 250, 210)
            screen.rectangle(x, y, 1, 1)
        for x, y, width, height, paper, shade, ribbon in wrapped:
            screen.pen = paper
            screen.rectangle(x, y, width, height)
            screen.pen = shade
            screen.rectangle(x, y + height - 1, width, 1)
            screen.pen = ribbon
            screen.rectangle(x + width // 2, y, 1, height)
            screen.rectangle(x, y + height // 2 - 1, width, 1)
    elif theme == "halloween":
        flickered = (flickered + 9 * step) % 6.2832
        night = 1 - sky.clamp(w["day"])
        for at, (x, y, half) in enumerate(PUMPKINS):
            glow = 0.84 + 0.16 * math.sin(flickered * (1 + at * 0.37) + at * 2)
            screen.pen = sky.pen(sky.mix(CARVED, sky.mix((0, 0, 0), CANDLE, glow), night))
            screen.rectangle(x - 3, y - 2, 2, 1)
            screen.rectangle(x + 1, y - 2, 2, 1)
            screen.rectangle(x - half + 2, y, half * 2 - 4, 1)
            screen.rectangle(x - 1, y + 1, 2, 1)
        bats(w, step)
    elif theme == "bonfire":
        FLAME_STATE[1] = int(step * 1000)
        FLAME_STATE[6] = BONFIRE[0] << 6
        FLAME_STATE[7] = (BONFIRE[1] - 2) << 6
        sparks(pixels, FLAME_PARTS, FLAME_STATE, sky.SINE)
