# the sky over the weather scenes, and the weather that falls through it. __init__ calls
# background, lights and clouds before the land, then fog, precipitation and lightning after
# it, every frame, each with the weather w and the seconds t since import. with the
# temperature in the middle, it asks for the far rain and snow before that and the near after.
#
# what doesn't move is drawn once and kept: the sky's gradient with its glows and the moon,
# and the clouds and fog as strips 256 px wide that slide across each frame. redrawing those
# is slow, so it's done a piece at a time, a few ms a frame, and shown once it's done
import math
import micropython
import time
from array import array
from random import getrandbits, randint, uniform

# a pixel's alpha byte fully on, written signed for viper
OPAQUE = const(-16777216)

# where __init__ hasn't said yet
HORIZON = const(70)

# the sun's middle across, and how high it rides by day. it sinks to the horizon at sunrise and
# sunset. its radius by day and at the horizon
SUN_X = const(96)
SUN_HIGH = const(22)
SUN_RADIUS = (7, 9)
# the rays: how many, how far they reach in px, how strong and how fast they turn, in degrees
# a second
RAYS = const(16)
RAY_REACH = 32
RAY_STRENGTH = 150
RAY_TURN = 3

MOON_X = const(30)
MOON_Y = const(22)
MOON_RADIUS = const(8)
MOON_HALO = 22
# points along each edge of the moon's shadow, its rim and the line between light and dark
MOON_SHADOW_STEPS = const(16)
# the shadow's rim reaches this far past the moon's, so no bright edge shows round it
MOON_SHADOW_OVERLAP = 0.7

# each kind of sky: its top, middle and horizon colours by day, then at night. then how much
# a sunset shows through it, 0 to 1
PALETTES = {
    "clear": ((22, 84, 184), (62, 138, 218), (150, 200, 238), (5, 8, 28), (12, 18, 48), (30, 42, 84), 1.0),
    "partly": ((30, 90, 180), (74, 142, 214), (158, 202, 234), (6, 9, 28), (13, 19, 46), (30, 41, 80), 1.0),
    "cloudy": ((64, 100, 150), (104, 138, 178), (168, 190, 212), (10, 13, 28), (18, 22, 42), (34, 40, 62), 0.7),
    "overcast": ((108, 116, 128), (136, 143, 153), (176, 181, 187), (14, 16, 24), (21, 24, 33), (36, 39, 50), 0.4),
    "fog": ((158, 163, 168), (180, 184, 188), (206, 209, 212), (30, 33, 40), (40, 44, 52), (58, 62, 70), 0.35),
    "drizzle": ((100, 108, 120), (126, 133, 143), (162, 168, 174), (14, 16, 24), (20, 23, 32), (34, 37, 48), 0.35),
    "rain": ((76, 84, 96), (102, 109, 120), (140, 146, 154), (12, 14, 21), (18, 20, 28), (30, 33, 43), 0.3),
    "showers": ((66, 88, 122), (108, 128, 156), (162, 176, 192), (10, 13, 26), (18, 22, 38), (32, 38, 58), 0.6),
    "snow": ((148, 154, 166), (174, 179, 189), (210, 214, 220), (22, 26, 38), (32, 37, 52), (54, 60, 78), 0.4),
    "storm": ((34, 38, 50), (54, 60, 74), (92, 98, 110), (9, 10, 17), (15, 17, 25), (28, 30, 40), 0.2),
}
# a sunset's top, middle and horizon colours, and how much of each shows at its height
DUSK = ((52, 44, 118), (196, 96, 118), (255, 158, 72))
DUSK_SHARE = (0.55, 0.75, 0.9)
# and its glow round where the sun meets the horizon: colour, strength and reach in px
DUSK_GLOW = ((255, 150, 70), 170, 60)

# skies too thick to see the sun, moon or stars through
HIDDEN = ("overcast", "fog", "drizzle", "rain", "snow", "storm")
# skies under a solid deck of cloud, rather than separate clouds
DECKS = ("overcast", "drizzle", "rain", "snow", "storm")

# clouds: each kind's lit tops and shaded bases by day
CLOUD_COLOURS = {
    "fair": ((252, 252, 255), (146, 158, 184)),
    "showers": ((226, 230, 238), (84, 92, 110)),
    "overcast": ((186, 191, 199), (100, 106, 118)),
    "drizzle": ((166, 172, 181), (90, 96, 108)),
    "rain": ((136, 142, 153), (62, 68, 80)),
    "snow": ((212, 216, 224), (140, 146, 160)),
    "storm": ((92, 98, 114), (28, 31, 42)),
}
# and at night, fair and under a deck
NIGHT_CLOUDS = ((66, 72, 96), (26, 30, 46))
NIGHT_DECK = ((46, 49, 62), (18, 20, 28))
# a sunset lights their tops and tints their bases
DUSK_CLOUDS = ((255, 176, 136), (118, 84, 116))

# the cloud strips' heights in px. the near one's clouds are big and high, the far one's small,
# low down by the horizon and hazy
NEAR_ROWS = const(58)
FAR_ROWS = const(26)
# drift per km/h of wind across, px a second, and the most and least. the far clouds move
# slower, as they're further off
DRIFT_PER_KMH = 0.12
MOST_DRIFT = 9
LEAST_DRIFT = 0.4
FAR_DRIFT = 0.45

# fog: its strip starts this far above the horizon and runs to the bottom. it thickens over
# FOG_RISE rows from the top, so it's thick over the far hills, stays thick to just past the
# horizon, then thins toward us, so the nearest ground shows more. it drifts at this share of
# the cloud's speed. its colour by day and night, thin and in its thicker banks
FOG_ABOVE = const(32)
FOG_RISE = const(14)
FOG_ROWS = const(128 - 64 + FOG_ABOVE)
FOG_DRIFT = 0.35
FOG_DAY = ((198, 203, 208), (226, 230, 234))
FOG_NIGHT = ((40, 44, 54), (58, 62, 74))
# its alpha where it's thickest and at the bottom, and how much its banks vary that (x16)
FOG_THICK = (215, 115)
FOG_BANKS = 6
# thinner than this, fog is just an even haze with no banks
FOG_EVEN = 0.45
# soft wisps that slide over the near ground at another speed: their height, and drift
WISP_ROWS = const(26)
WISP_DRIFT = 1.6

# rain at each level 1-3: drops. then per depth layer, far to near: speed in px a second,
# streak length in px and how strong it is, 0-255
RAIN_LEVELS = (
    (50, ((55, 2, 60), (75, 3, 90), (100, 3, 120))),
    (100, ((85, 3, 60), (115, 4, 95), (150, 6, 135))),
    (150, ((110, 4, 70), (150, 5, 105), (195, 8, 150))),
)
RAIN_DAY = (205, 218, 238)
RAIN_NIGHT = (96, 106, 132)
# rain and snow in front of something as bright as they are, or within CLOSE of it, wouldn't
# show, so there they're drawn as shadows: their own colour, this much towards this one
CLOSE = const(40)
RAIN_SHADOW = ((20, 35, 70), 0.7)
SNOW_SHADOW = ((50, 70, 120), 0.6)
# sideways px per px of fall, per km/h across, and the most
SLANT_PER_KMH = 0.018
MOST_SLANT = 0.85
# gusts swing the rain this much more, per km/h the gusts beat the wind
GUST_SLANT_PER_KMH = 0.008

# snow at each level 1-3: flakes. layers, far to near: speed in px a second, and pen strength
SNOW_LEVELS = (50, 100, 160)
SNOW_LAYERS = ((11, 150), (17, 215), (24, 240))
SNOW_DAY = (255, 255, 255)
SNOW_NIGHT = (176, 186, 212)
# drift per km/h across, px a second, and the most. then how far each side flakes sway, in px
SNOW_DRIFT_PER_KMH = 0.5
MOST_SNOW_DRIFT = 34
SNOW_SWAY = 3

# hail: stones, gravity in px a second each second, speed leaving the cloud. each lands on the
# ground somewhere between the horizon and the bottom, then bounces once
HAIL_STONES = const(40)
HAIL_GRAVITY = 420
HAIL_SPEED = (70, 110)
HAIL_PEN = (236, 242, 255)

# lightning: seconds between strikes. the flash's strength over its first moments, seconds
# and strength, eased between
STRIKE_GAP = (3.5, 9)
FLASH = ((0.0, 1.0), (0.05, 1.0), (0.07, 0.2), (0.11, 0.2), (0.13, 0.85), (0.2, 0.5), (0.45, 0.0))
BOLT_SHOWS = 0.3
FLASH_PEN = (200, 210, 255)
BOLT_GLOW = (170, 185, 255)


# rows of the sky kept, past the lowest horizon __init__ may give
SKY_ROWS = const(84)

# each frame spends about this long redrawing at most, in us, a chunk of rows at a time
WORK_US = const(3000)
CHUNK = const(12)


def mix(start, end, amount):
    return (start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount,
            start[2] + (end[2] - start[2]) * amount)


def pen(rgb, alpha=255):
    return color.rgb(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(alpha))


def pack(rgb):
    return (int(rgb[2]) << 16) | (int(rgb[1]) << 8) | int(rgb[0])


def clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


# the light changes in these steps
def steps(value, count):
    return int(value * count + 0.5)


# how much of the sun, moon and stars shows through the sky, 0-1
def clearness(w):
    if w["sky"] in HIDDEN or w["storm"]:
        return 0.0
    see = clamp(1 - (w["cloud"] - 40) / 60)
    return min(see, 0.6) if w["sky"] in ("cloudy", "showers") else see


# the sky's top, middle and horizon colours, and how much sunset there is
def sky_colours(w):
    palette = PALETTES.get(w["sky"], PALETTES["clear"])
    day = clamp(w["day"])
    # sunsets are muted by cloud, and dimmer once the sun is down
    warmth = clamp(w["dusk"]) * palette[6]
    stops = []
    for band in range(3):
        colour = mix(palette[band + 3], palette[band], day)
        dusk = mix((0, 0, 0), DUSK[band], 0.3 + 0.7 * day)
        stops.append(mix(colour, dusk, warmth * DUSK_SHARE[band]))
    return stops, warmth


# --- redrawing a piece at a time ---

# each kind of redraw waiting, as a generator that does a piece each time it's stepped
JOBS = ("sky", "clouds", "fog")
jobs = {}


# steps the jobs in order until they're done or the time's up
def work(budget):
    start = time.ticks_us()
    for name in JOBS:
        job = jobs.get(name)
        while job is not None:
            try:
                next(job)
            except StopIteration:
                del jobs[name]
                job = None
            if time.ticks_diff(time.ticks_us(), start) > budget:
                return


# --- noise for the clouds and fog ---

# grey noise from picovector's fractal brush, drawn into a strip we need anyway, then copied
# out a byte a pixel. hist counts each value, to find thresholds by
@micropython.viper
def grab(source: ptr8, out: ptr8, count: int, hist: ptr32):  # noqa: F821
    at = 0
    while at < count:
        value = source[at << 2]
        out[at] = value
        hist[value] += 1
        at += 1


# the noise value below which each percent of it lies
def percentiles(hist, count):
    levels = bytearray(101)
    below = 0
    percent = 0
    for value in range(256):
        below += hist[value]
        while percent <= 100 and below * 100 >= percent * count:
            levels[percent] = value
            percent += 1
    return levels


# a strip of cloud or fog 256 px wide, slid across the screen and wrapped round. paint colours
# it from the noise. rows holds two numbers for each of its rows, and settings the rest, for
# paint. it shows rows first to last, its top at top on screen
class Strip:
    def __init__(self, height, paint):
        self.image = image(256, height)
        self.height = height
        self.paint = paint
        self.rows = array("i", [0] * height * 2)
        self.settings = array("i", [0] * 10)
        self.ramp = array("i", [0] * 256)
        self.shows = False
        self.first = 0
        self.last = height
        self.top = 0
        # how far it has drifted, in px, within its width
        self.at = 0.0

    # redraws the rows it shows, handing back after each chunk
    def redraw(self):
        row = self.first
        while row < self.last:
            self.settings[0] = row
            self.settings[1] = min(row + CHUNK, self.last)
            self.paint(memoryview(self.image), self.noise, self.rows, self.settings, self.ramp)
            row += CHUNK
            yield

    def move(self, by):
        self.at = (self.at + by) % 256

    def slide(self):
        if not self.shows:
            return
        height = self.last - self.first
        left = -int(self.at) % 256
        across = min(128, 256 - left)
        y = self.top + self.first
        screen.blit(self.image, rect(left, self.first, across, height), rect(0, y, across, height))
        if across < 128:
            screen.blit(self.image, rect(0, self.first, 128 - across, height), rect(across, y, 128 - across, height))


# colours in a ramp from lit to dark, 256 steps
@micropython.viper
def make_ramp(ramp: ptr32, lit: int, dark: int):  # noqa: F821
    lit_red = lit & 0xff
    lit_green = (lit >> 8) & 0xff
    lit_blue = (lit >> 16) & 0xff
    dark_red = dark & 0xff
    dark_green = (dark >> 8) & 0xff
    dark_blue = (dark >> 16) & 0xff
    step = 0
    while step < 256:
        red = lit_red + (((dark_red - lit_red) * step) >> 8)
        green = lit_green + (((dark_green - lit_green) * step) >> 8)
        blue = lit_blue + (((dark_blue - lit_blue) * step) >> 8)
        ramp[step] = (blue << 16) | (green << 8) | red
        step += 1


# colours rows first to last of a cloud strip from the noise. every other pixel is worked out,
# and those between are the average of their neighbours, which is half the work. picovector
# wants each pixel's colour already scaled by its alpha. rows holds, for each row, what's
# added to the noise before it counts as cloud (below 0 is clear sky) and the most its alpha
# can be. settings: first and last row, step across and down the noise, how far above to look
# for cloud that shades this bit, how fast cloud turns solid past its edge (x16), how much
# cloud above darkens it and how much thicker cloud does (x16), and the shade to start from
@micropython.viper
def paint_clouds(out: ptr32, noise: ptr8, rows: ptr32, settings: ptr32, ramp: ptr32):  # noqa: F821
    y = int(settings[0])
    last = int(settings[1])
    step_x = int(settings[2]) << 1
    step_y = int(settings[3])
    reach = int(settings[4])
    gain = int(settings[5])
    shade_gain = int(settings[6])
    thick_gain = int(settings[7])
    shade_base = int(settings[8])
    # each byte's top 7 bits, for halving four at once
    halves = 0x7f7f
    halves = (halves << 16) | halves
    while y < last:
        bias = int(rows[y * 2])
        cap = int(rows[y * 2 + 1])
        at = y << 8
        end = at + 256
        if bias <= -255 or cap <= 0:
            while at < end:
                out[at] = 0
                at += 1
        else:
            source = (y * step_y) << 8
            above = y - reach
            if above < 0:
                above = 0
            above_source = (above * step_y) << 8
            above_bias = int(rows[above * 2])
            start = at
            column = 0
            before = 0
            first = 0
            while at < end:
                colour = 0
                depth = int(noise[source + column]) + bias
                if depth > 0:
                    alpha = (depth * gain) >> 4
                    if alpha > 255:
                        alpha = 255
                    if cap < 255:
                        alpha = (alpha * cap) >> 8
                    over = int(noise[above_source + column]) + above_bias
                    if over < 0:
                        over = 0
                    shade = shade_base + ((over * shade_gain + depth * thick_gain) >> 4)
                    if shade > 255:
                        shade = 255
                    elif shade < 0:
                        shade = 0
                    colour = int(ramp[shade])
                    if alpha < 255:
                        colour = ((((colour & 0xff00ff) * alpha) >> 8) & 0xff00ff) | ((((colour & 0xff00) * alpha) >> 8) & 0xff00)
                    colour |= alpha << 24
                out[at] = colour
                if at == start:
                    first = colour
                else:
                    out[at - 1] = ((before >> 1) & halves) + ((colour >> 1) & halves) + (before & colour & 0x01010101)
                before = colour
                at += 2
                column = (column + step_x) & 255
            out[end - 1] = ((before >> 1) & halves) + ((first >> 1) & halves) + (before & first & 0x01010101)
        y += 1


# colours rows first to last of a fog strip, every other pixel as for the clouds. rows holds,
# for each row, its alpha where the noise is middling and how much the noise moves that (x16).
# settings: first and last row, step across the noise, the noise row to start at and the
# noise's middle. the ramp runs from thin fog to thick
@micropython.viper
def paint_fog(out: ptr32, noise: ptr8, rows: ptr32, settings: ptr32, ramp: ptr32):  # noqa: F821
    y = int(settings[0])
    last = int(settings[1])
    step_x = int(settings[2]) << 1
    first_row = int(settings[3])
    middle = int(settings[4])
    halves = 0x7f7f
    halves = (halves << 16) | halves
    while y < last:
        base = int(rows[y * 2])
        gain = int(rows[y * 2 + 1])
        source = ((y + first_row) & 63) << 8
        at = y << 8
        end = at + 256
        start = at
        column = 0
        before = 0
        first = 0
        while at < end:
            colour = 0
            lump = int(noise[source + column]) - middle
            alpha = base + ((lump * gain) >> 4)
            if alpha > 0:
                if alpha > 255:
                    alpha = 255
                light = 128 + lump * 2
                if light < 0:
                    light = 0
                elif light > 255:
                    light = 255
                colour = int(ramp[light])
                colour = (alpha << 24) | ((((colour & 0xff00ff) * alpha) >> 8) & 0xff00ff) | ((((colour & 0xff00) * alpha) >> 8) & 0xff00)
            out[at] = colour
            if at == start:
                first = colour
            else:
                out[at - 1] = ((before >> 1) & halves) + ((colour >> 1) & halves) + (before & colour & 0x01010101)
            before = colour
            at += 2
            column = (column + step_x) & 255
        out[end - 1] = ((before >> 1) & halves) + ((first >> 1) & halves) + (before & first & 0x01010101)
        y += 1


# a band of separate clouds. inside rows top to bottom the noise counts as cloud past
# threshold. above, that fades by soft_step a row, below by hard_step, so clouds have domed
# tops and flatter bases. cap is the most any row's alpha can be.
# shape: height, threshold, top, bottom, soft_step, hard_step and cap
@micropython.viper
def fill_band(rows: ptr32, shape: ptr32):  # noqa: F821
    height = int(shape[0])
    threshold = int(shape[1])
    top = int(shape[2])
    bottom = int(shape[3])
    soft_step = int(shape[4])
    hard_step = int(shape[5])
    cap = int(shape[6])
    row = 0
    while row < height:
        bias = 0 - threshold
        if row < top:
            bias -= (top - row) * soft_step
        elif row > bottom:
            bias -= (row - bottom) * hard_step
        rows[row * 2] = bias
        rows[row * 2 + 1] = cap
        row += 1


# a solid deck of cloud, fading out over fade rows down to bottom. shape: height, what's added
# to the noise, bottom and fade
@micropython.viper
def fill_deck(rows: ptr32, shape: ptr32):  # noqa: F821
    height = int(shape[0])
    bias = int(shape[1])
    bottom = int(shape[2])
    fade = int(shape[3])
    row = 0
    while row < height:
        cap = ((bottom - row) * 255) // fade
        rows[row * 2] = bias
        rows[row * 2 + 1] = 0 if cap < 0 else 255 if cap > 255 else cap
        row += 1


# fog: smoothly thicker over FOG_RISE rows from its top, thickest over the far hills to just
# past the horizon, then thinning toward us. its banks fade in over its top rows too.
# shape: height, top and horizon on screen, density x256, thickness where it's thickest and at
# the bottom, and how much the banks show (x16)
@micropython.viper
def fill_fog(rows: ptr32, shape: ptr32):  # noqa: F821
    height = int(shape[0])
    top = int(shape[1])
    horizon = int(shape[2])
    density = int(shape[3])
    thickest = int(shape[4])
    nearest = int(shape[5])
    banks = int(shape[6])
    row = 0
    while row < height:
        y = top + row
        if row < FOG_RISE:
            rise = (row << 8) // FOG_RISE
            base = (thickest * ((rise * rise * (768 - 2 * rise)) >> 16)) >> 8
        elif y <= horizon + 6:
            base = thickest
        else:
            base = thickest - ((thickest - nearest) * (y - horizon - 6)) // (121 - horizon)
        show = row if row < 10 else 10
        rows[row * 2] = (base * density) >> 8
        rows[row * 2 + 1] = (banks * show * density) // 2560
        row += 1


NEAR = Strip(NEAR_ROWS, paint_clouds)
FAR = Strip(FAR_ROWS, paint_clouds)
FOG = Strip(FOG_ROWS, paint_fog)
WISPS = Strip(WISP_ROWS, paint_fog)
SHAPE = array("i", [0] * 8)

# cloud cells 32 px wide by 16 high. fog's are 64 by 8 and smooth, so it lies in soft banks.
# they repeat every 32 rows
NEAR.image.pen = brush.fractal(16, 3, 0.5, 8, getrandbits(16), mat3().scale(2, 1))
NEAR.image.clear()
NEAR.noise = FAR.noise = bytearray(256 * NEAR_ROWS)
counts = array("i", [0] * 256)
grab(memoryview(NEAR.image), NEAR.noise, 256 * NEAR_ROWS, counts)
CLOUD_LEVELS = percentiles(counts, 256 * NEAR_ROWS)

FOG.image.pen = brush.fractal(8, 2, 0.45, 4, getrandbits(16), mat3().scale(8, 1))
FOG.image.clear()
FOG.noise = WISPS.noise = bytearray(256 * 64)
counts = array("i", [0] * 256)
grab(memoryview(FOG.image), FOG.noise, 256 * 64, counts)
FOG_MIDDLE = percentiles(counts, 256 * 64)[50]
del counts


# --- the sky: its gradient, the glows of the sun and sunset, and the moon ---

# shown, and the one being drawn, swapped when it's done
SKY = image(128, SKY_ROWS)
BACK = image(128, SKY_ROWS)
SKY.antialias = BACK.antialias = image.X4
sky_ready = False
# rows of SKY copied to the screen, past the horizon a little. below them the screen is filled
# with the horizon's colour
sky_rows = HORIZON + 6
ground_pen = color.rgb(0, 0, 0)
# what's set with each sky: how strong the sun and stars are, the sun's place and its brushes
sun_show = 0.0
sun_at = vec2(SUN_X, SUN_HIGH)
sun_radius = SUN_RADIUS[0]
sun_brush = None
ray_brush = None
star_level = 0

# the moon's shadow: round its rim, then back along where light meets dark
RIM = [(math.sin(math.pi * step / MOON_SHADOW_STEPS), math.cos(math.pi * step / MOON_SHADOW_STEPS)) for step in range(MOON_SHADOW_STEPS + 1)]
# 4 px blobs, 3 octaves, persistence 0.5, no tiling
MOON_CRATERS = brush.fractal(4, 3, 0.5, 0, 311)
MOON_CRATERS.ramp(((0.0, color.rgb(150, 150, 140)), (0.55, color.rgb(228, 226, 214)), (1.0, color.rgb(232, 230, 218))))


# draws the next sky into BACK a piece at a time, then shows it
def sky_job(w):
    global SKY, BACK, sky_ready, sky_rows, ground_pen, sun_show, sun_at, sun_radius, sun_brush, ray_brush, star_level
    horizon = w.get("horizon", HORIZON)
    day = clamp(w["day"])
    low = clamp(w["dusk"])
    see = clearness(w)
    phase = w["moon"]
    south = w.get("south", False)
    stops, warmth = sky_colours(w)
    BACK.pen = brush.gradient(brush.LINEAR, 0, 0, 0, horizon, ((0.0, pen(stops[0])), (0.55, pen(stops[1])), (1.0, pen(stops[2]))))
    BACK.clear()
    yield

    if warmth > 0.02:
        glow, strength, reach = DUSK_GLOW
        BACK.pen = brush.gradient(brush.RADIAL, SUN_X, horizon, SUN_X, horizon + reach,
                                  ((0.0, pen(glow, strength * warmth * (0.4 + 0.6 * day))), (1.0, pen(glow, 0))))
        BACK.circle(SUN_X, horizon, reach)
        yield

    # the sun rides high by day and sits on the horizon at sunrise and sunset
    at = vec2(SUN_X, SUN_HIGH + (horizon - 13 - SUN_HIGH) * low)
    radius = SUN_RADIUS[0] + (SUN_RADIUS[1] - SUN_RADIUS[0]) * low
    show = clamp(day * 2.5 - 0.25) * see
    disc = rays = None
    if show > 0.02:
        core = mix((255, 252, 230), (255, 206, 130), low)
        rim = mix((255, 216, 96), (255, 120, 48), low)
        # a soft glow round it, kept in the sky
        BACK.pen = brush.gradient(brush.RADIAL, at.x, at.y, at.x, at.y + 26, ((0.0, pen(core, 110 * show)), (1.0, pen(core, 0))))
        BACK.circle(at.x, at.y, 26)
        disc = brush.gradient(brush.RADIAL, at.x, at.y, at.x, at.y + radius,
                              ((0.0, pen(core, 255 * show)), (0.6, pen(core, 255 * show)), (1.0, pen(rim, 255 * show))))
        rays = brush.gradient(brush.RADIAL, at.x, at.y, at.x, at.y + RAY_REACH,
                              ((0.0, pen(core, RAY_STRENGTH * show * (1 - 0.5 * low))), (1.0, pen(core, 0))))
        yield

    night = clamp(1 - day * 1.6)
    moon_show = see * clamp(1.2 - day * 1.6)
    if moon_show > 0.02:
        draw_moon(phase, south, moon_show, mix(stops[0], stops[1], MOON_Y / (horizon * 0.55)))

    SKY, BACK = BACK, SKY
    sky_ready = True
    sky_rows = min(SKY_ROWS, horizon + 6)
    ground_pen = pen(stops[2])
    sun_show, sun_at, sun_radius, sun_brush, ray_brush = show, at, radius, disc, rays
    star_level = int(255 * see * night * night)


# the moon in its phase: a halo, the cratered disc, then its shadow, in the sky's own colour
# with a little earthshine showing through
def draw_moon(phase, south, show, behind):
    # 1 at the lit edge, -1 at the dark one, where light meets dark across it
    squash = math.cos(phase * 2 * math.pi)
    lit = (1 - squash) / 2
    BACK.pen = brush.gradient(brush.RADIAL, MOON_X, MOON_Y, MOON_X, MOON_Y + MOON_HALO,
                              ((0.0, color.rgb(170, 180, 220, int(130 * show * lit))), (1.0, color.rgb(170, 180, 220, 0))))
    BACK.circle(MOON_X, MOON_Y, MOON_HALO)
    BACK.pen = MOON_CRATERS
    BACK.alpha = int(255 * show)
    BACK.circle(MOON_X, MOON_Y, MOON_RADIUS)
    BACK.alpha = 255
    if lit > 0.98:
        return
    # dark on the left while it waxes, as seen from the northern half of the world. the other
    # way round south of the equator
    side = -1 if (phase < 0.5) != south else 1
    rim = MOON_RADIUS + MOON_SHADOW_OVERLAP
    across = side * rim
    bulge = -side * squash * MOON_RADIUS
    outline = [vec2(MOON_X + across * sin, MOON_Y - rim * cos) for sin, cos in RIM]
    outline += [vec2(MOON_X + bulge * sin, MOON_Y - rim * cos) for sin, cos in reversed(RIM)]
    BACK.pen = pen(mix(behind, (26, 32, 58), 0.25), 225 * show)
    BACK.shape(shape.custom(outline))


# t gets coarse after days running, as floats here are short, so things move by a clock of
# their own: seconds since the last frame, from the ticks. anything that turns or drifts is
# kept within its own period, for the same reason
dt = 0.0
last_tick = None
seen = None
sky_key = None
cloud_key = None
fog_key = None


# starts redrawing whatever the weather or the light has changed
def plan(w, day, dusk):
    global sky_key, cloud_key, fog_key
    horizon = w.get("horizon", HORIZON)
    key = (day, dusk, w["sky"], w["cloud"] // 5, w["storm"], round(w["moon"], 2), w.get("south", False), horizon)
    if key != sky_key:
        sky_key = key
        jobs["sky"] = sky_job(w)
    # the clouds and fog follow the light in coarser steps. a change of weather hides them
    # until they're redrawn, as does one that comes before the last redraw is done
    light = (day // 2, dusk // 2)
    key = ((w["sky"], w["cloud"], w["storm"], horizon), light)
    if key != cloud_key:
        reshape = cloud_key is None or key[0] != cloud_key[0] or "clouds" in jobs
        cloud_key = key
        jobs["clouds"] = cloud_job(w, reshape)
    key = ((round(w["fog"], 2), horizon), light)
    if key != fog_key:
        reshape = fog_key is None or key[0] != fog_key[0] or "fog" in jobs
        fog_key = key
        jobs["fog"] = fog_job(w, reshape)


def background(w, t):  # noqa: ARG001
    global seen, dt, last_tick
    now = time.ticks_ms()
    dt = 0.0 if last_tick is None else clamp(time.ticks_diff(now, last_tick) / 1000, 0, 0.25)
    last_tick = now
    day = steps(w["day"], 64)
    dusk = steps(w["dusk"], 64)
    if w["change"] != seen or sky_key[0] != day or sky_key[1] != dusk:
        seen = w["change"]
        plan(w, day, dusk)
    if jobs:
        # with no sky yet, the first is drawn whole
        if not sky_ready:
            for _ in jobs.pop("sky"):
                pass
        work(WORK_US)
    size = sky_rows << 9
    memoryview(screen)[0:size] = memoryview(SKY)[0:size]
    screen.pen = ground_pen
    screen.rectangle(0, sky_rows, 128, 128 - sky_rows)


# --- the sun's rays and the stars ---

paths = []
for ray in range(RAYS):
    start = 2 * math.pi * ray / RAYS
    end = 2 * math.pi * (ray + 0.45) / RAYS
    paths.append([vec2(0, 0), vec2(math.cos(start) * RAY_REACH, math.sin(start) * RAY_REACH),
                  vec2(math.cos(end) * RAY_REACH, math.sin(end) * RAY_REACH)])
SUN_RAYS = shape.custom(*paths)
del paths

# stars: where each is on screen, how bright 0-255 and its twinkle phase. more of them high
# up, none round the moon or near the lowest horizon
STARS = const(56)
STAR_FIELD = array("i", [0] * STARS * 3)
star = 0
while star < STARS:
    x = getrandbits(7)
    y = int(60 * uniform(0, 1) ** 1.4)
    if (x - MOON_X) ** 2 + (y - MOON_Y) ** 2 > 14 * 14:
        STAR_FIELD[star * 3] = (y << 7) | x
        STAR_FIELD[star * 3 + 1] = 70 + getrandbits(7) + (getrandbits(6) if star % 5 == 0 else 0)
        STAR_FIELD[star * 3 + 2] = getrandbits(10)
        star += 1


# adds each star's light to the sky under it, twinkling. stops at limit, the pixel the
# horizon's row starts at
@micropython.viper
def twinkle(pixels: ptr32, stars: ptr32, spin: int, level: int, limit: int):  # noqa: F821
    star = 0
    while star < STARS:
        at = int(stars[star * 3])
        if at < limit:
            phase = (int(stars[star * 3 + 2]) + spin) & 1023
            wave = phase if phase < 512 else 1023 - phase
            light = (((int(stars[star * 3 + 1]) * (130 + (wave >> 2))) >> 8) * level) >> 8
            under = int(pixels[at])
            red = (under & 0xff) + light
            green = ((under >> 8) & 0xff) + light
            blue = ((under >> 16) & 0xff) + light + (light >> 3)
            pixels[at] = OPAQUE | ((255 if blue > 255 else blue) << 16) | ((255 if green > 255 else green) << 8) | (255 if red > 255 else red)
        star += 1


# how far the stars' twinkle and the sun's rays have turned. the rays repeat every 360 / RAYS
twinkled = 0.0
turned = 0.0


def lights(w, t):  # noqa: ARG001
    global twinkled, turned
    if star_level:
        twinkled = (twinkled + 300 * dt) % 1024
        twinkle(memoryview(screen), STAR_FIELD, int(twinkled), star_level, (w.get("horizon", HORIZON) - 4) << 7)
    if sun_show > 0.02:
        turned = (turned + RAY_TURN * dt) % (360 / RAYS)
        smooth = screen.antialias
        # the rays fade out anyway, so they skip antialiasing, which would triple their cost
        screen.antialias = image.OFF
        SUN_RAYS.transform = mat3.trs(sun_at, turned)
        screen.pen = ray_brush
        screen.shape(SUN_RAYS)
        screen.antialias = image.X4
        screen.pen = sun_brush
        screen.circle(sun_at.x, sun_at.y, sun_radius)
        screen.antialias = smooth


# --- clouds ---

def set_clouds(strip, settings, lit, dark):
    for at in range(len(settings)):
        strip.settings[at + 2] = settings[at]
    make_ramp(strip.ramp, pack(lit), pack(dark))


def band(strip, threshold, top, bottom, soft, hard, cap=255):
    SHAPE[0] = strip.height
    SHAPE[1] = threshold
    SHAPE[2] = top
    SHAPE[3] = bottom
    SHAPE[4] = 120 // soft
    SHAPE[5] = 120 // hard
    SHAPE[6] = cap
    fill_band(strip.rows, SHAPE)
    # the rows that can have any cloud in
    strip.first = max(0, top - (255 - threshold) // SHAPE[4])
    strip.last = min(strip.height, bottom + (255 - threshold) // SHAPE[5] + 1)


# works out how both cloud strips should look. false if there's no cloud to show
def plan_clouds(w):
    horizon = w.get("horizon", HORIZON)
    kind = w["sky"]
    day = clamp(w["day"])
    stops, warmth = sky_colours(w)
    cover = clamp(w["cloud"] / 100)
    if kind == "clear":
        cover = min(cover, 0.12)
    elif kind == "partly":
        cover = clamp(cover, 0.25, 0.55)
    elif kind == "cloudy":
        cover = clamp(cover, 0.55, 0.85)
    elif kind == "showers":
        cover = clamp(cover, 0.6, 0.9)
    is_deck = kind in DECKS or w["storm"]
    if kind == "fog" or (not is_deck and cover < 0.02):
        return False

    name = "storm" if w["storm"] else kind if kind in CLOUD_COLOURS else "fair"
    lit, dark = CLOUD_COLOURS[name]
    night = NIGHT_DECK if is_deck else NIGHT_CLOUDS
    lit = mix(night[0], lit, day)
    dark = mix(night[1], dark, day)
    lit = mix(lit, mix((0, 0, 0), DUSK_CLOUDS[0], 0.4 + 0.6 * day), warmth * 0.7)
    dark = mix(dark, mix((0, 0, 0), DUSK_CLOUDS[1], 0.4 + 0.6 * day), warmth * 0.5)

    threshold = CLOUD_LEVELS[100 - int(cover * 100)]
    if is_deck:
        # darker where it's thicker, fading out above the horizon. lower in rain
        bottom = min(NEAR_ROWS, horizon - (10 if name in ("rain", "storm") else 16))
        SHAPE[0] = NEAR_ROWS
        SHAPE[1] = 255 - CLOUD_LEVELS[50]
        SHAPE[2] = bottom
        SHAPE[3] = 22
        fill_deck(NEAR.rows, SHAPE)
        NEAR.first = 0
        NEAR.last = bottom
        set_clouds(NEAR, (1, 1, 4, 16, 3, 8, 10), lit, dark)
    else:
        band(NEAR, threshold, 6, horizon - 30, 8, 3)
        set_clouds(NEAR, (1, 1, 5, 56, 22, 0, 0), lit, dark)

    # far off: smaller clouds low down, hazy with the horizon's colour. under a deck, ragged
    # dark scud
    FAR.top = horizon - FAR_ROWS
    if is_deck:
        band(FAR, CLOUD_LEVELS[55], 10, FAR_ROWS - 6, 6, 4, 200)
        set_clouds(FAR, (2, 2, 2, 40, 30, 0, 60), mix(lit, dark, 0.5), dark)
    else:
        band(FAR, threshold, 6, FAR_ROWS - 7, 5, 2, 220)
        set_clouds(FAR, (2, 2, 3, 56, 22, 0, 0), mix(lit, stops[2], 0.3), mix(dark, stops[2], 0.45))
    return True


def cloud_job(w, reshape):
    if reshape:
        NEAR.shows = FAR.shows = False
    if not plan_clouds(w):
        NEAR.shows = FAR.shows = False
        return
    yield
    yield from NEAR.redraw()
    NEAR.shows = True
    yield from FAR.redraw()
    FAR.shows = True


# how fast the wind moves cloud across, px a second. + is to the right
def drift(w):
    speed = w["push"] * DRIFT_PER_KMH
    if -LEAST_DRIFT < speed < LEAST_DRIFT:
        speed = -LEAST_DRIFT if speed < 0 else LEAST_DRIFT
    return clamp(speed, -MOST_DRIFT, MOST_DRIFT)


def clouds(w, t):  # noqa: ARG001
    speed = drift(w) * dt
    NEAR.move(speed)
    FAR.move(speed * FAR_DRIFT)
    FAR.slide()
    NEAR.slide()


# --- fog ---

# light fog is an even haze, drawn with this brush from haze_top down
haze = None
haze_top = HORIZON
# how much each row of the wisps shows, strongest in their middle
WISP_EDGE = [1 - abs(row - WISP_ROWS / 2) / (WISP_ROWS / 2) for row in range(WISP_ROWS)]


def fog_job(w, reshape):
    global haze, haze_top
    density = clamp(w["fog"])
    if reshape or density < FOG_EVEN:
        FOG.shows = WISPS.shows = False
    haze = None
    if density < 0.02:
        return
    horizon = w.get("horizon", HORIZON)
    day = clamp(w["day"])
    thin = mix(FOG_NIGHT[0], FOG_DAY[0], day)
    thick = mix(FOG_NIGHT[1], FOG_DAY[1], day)
    warmth = clamp(w["dusk"]) * 0.35
    thin = mix(thin, mix(thin, DUSK[2], 0.5), warmth)
    thick = mix(thick, mix(thick, DUSK[2], 0.5), warmth)
    FOG.top = horizon - FOG_ABOVE
    if density < FOG_EVEN:
        haze_top = FOG.top
        span = 128 - haze_top
        haze = brush.gradient(brush.LINEAR, 0, haze_top, 0, 128, ((0.0, pen(thin, 0)), (FOG_RISE / span, pen(thin, FOG_THICK[0] * density)),
                                                                   ((FOG_ABOVE + 6) / span, pen(thin, FOG_THICK[0] * density)),
                                                                   (1.0, pen(thin, FOG_THICK[1] * density))))
        return

    SHAPE[0] = FOG_ROWS
    SHAPE[1] = FOG.top
    SHAPE[2] = horizon
    SHAPE[3] = int(density * 256)
    SHAPE[4], SHAPE[5] = FOG_THICK
    SHAPE[6] = FOG_BANKS
    fill_fog(FOG.rows, SHAPE)
    FOG.first = 0
    FOG.last = min(FOG_ROWS, 128 - FOG.top)
    FOG.settings[2] = 1
    FOG.settings[3] = 0
    FOG.settings[4] = FOG_MIDDLE
    make_ramp(FOG.ramp, pack(thin), pack(thick))
    yield
    yield from FOG.redraw()
    FOG.shows = True

    # soft wisps over the near ground, sliding at their own pace
    WISPS.top = horizon + 14
    rows = WISPS.rows
    for row in range(WISP_ROWS):
        rows[row * 2] = int(-30 + 30 * WISP_EDGE[row] * density)
        rows[row * 2 + 1] = int(26 * WISP_EDGE[row] * density)
    WISPS.first = 0
    WISPS.last = min(WISP_ROWS, 128 - WISPS.top)
    WISPS.settings[2] = 2
    WISPS.settings[3] = 20
    WISPS.settings[4] = FOG_MIDDLE
    make_ramp(WISPS.ramp, pack(thick), pack(thick))
    yield
    yield from WISPS.redraw()
    WISPS.shows = True


def fog(w, t):  # noqa: ARG001
    if haze is not None:
        screen.pen = haze
        screen.rectangle(0, haze_top, 128, 128 - haze_top)
        return
    speed = drift(w) * FOG_DRIFT * dt
    FOG.move(speed)
    WISPS.move(speed * WISP_DRIFT)
    FOG.slide()
    WISPS.slide()


# --- rain, snow and hail ---

# rain drops: x and y in 1/64 px, and their layer 0-2, far to near
RAIN_MOST = const(150)
DROPS = array("i", [0] * RAIN_MOST * 3)
for drop in range(RAIN_MOST):
    DROPS[drop * 3] = getrandbits(13)
    DROPS[drop * 3 + 1] = getrandbits(13)
    DROPS[drop * 3 + 2] = drop % 3
# per layer: fall and drift this frame in 1/64 px, streak length, slant in 1/256 px across per
# px down, pen strength, how much it fades each px up the streak and the row a drop's head
# leaves the screen at, in 1/64 px
RAIN_STEP = array("i", [0] * 21)
# drops to draw, colour, a random seed carried between frames, and the layers to move and
# draw, first to last. then the shadow's colour, and the screen rows ink is on, from and to
RAIN_STATE = array("i", [0, 0, getrandbits(30), 0, 2, 0, 0, 0])


# ink is an image as wide as the screen that the rain falls in front of. over its solid
# parts, rain that wouldn't show is drawn as shadow
@micropython.viper
def rain(pixels: ptr32, drops: ptr32, layers: ptr32, state: ptr32, ink: ptr32):  # noqa: F821
    count = int(state[0])
    colour = int(state[1])
    seed = int(state[2])
    rain_red = colour & 0xff
    rain_green = (colour >> 8) & 0xff
    rain_blue = (colour >> 16) & 0xff
    first = int(state[3])
    last = int(state[4])
    colour = int(state[5])
    shadow_red = colour & 0xff
    shadow_green = (colour >> 8) & 0xff
    shadow_blue = (colour >> 16) & 0xff
    ink_from = int(state[6])
    ink_to = int(state[7])
    drop = 0
    while drop < count:
        at = drop * 3
        layer = int(drops[at + 2])
        if layer < first or layer > last:
            drop += 1
            continue
        layer *= 7
        x = int(drops[at]) + int(layers[layer + 1])
        y = int(drops[at + 1]) + int(layers[layer])
        # off the bottom: back above the top somewhere new
        if y >= int(layers[layer + 6]):
            seed = seed * 1664525 + 1013904223
            y = -((seed >> 20) & 0x3ff)
            x = (seed >> 7) & 8191
        x &= 8191
        drops[at] = x
        drops[at + 1] = y
        length = int(layers[layer + 2])
        slant = int(layers[layer + 3])
        alpha = int(layers[layer + 4])
        fade = int(layers[layer + 5])
        row = y >> 6
        column = x << 2
        while length > 0 and row >= 0:
            if row < 128:
                spot = (row << 7) | ((column >> 8) & 127)
                under = int(pixels[spot])
                red = under & 0xff
                green = (under >> 8) & 0xff
                blue = (under >> 16) & 0xff
                if row >= ink_from and row < ink_to and green + CLOSE > rain_green and ((int(ink[spot - (ink_from << 7)]) >> 24) & 0xff) > 128:
                    pixels[spot] = OPAQUE | ((blue + (((shadow_blue - blue) * alpha) >> 8)) << 16) | ((green + (((shadow_green - green) * alpha) >> 8)) << 8) | (red + (((shadow_red - red) * alpha) >> 8))
                else:
                    pixels[spot] = OPAQUE | ((blue + (((rain_blue - blue) * alpha) >> 8)) << 16) | ((green + (((rain_green - green) * alpha) >> 8)) << 8) | (red + (((rain_red - red) * alpha) >> 8))
            row -= 1
            column -= slant
            alpha -= fade
            length -= 1
        drop += 1
    state[2] = seed


# snow flakes: x and y in 1/64 px, layer 0-2, speed x256 of their layer's and sway phase
SNOW_MOST = const(160)
FLAKES = array("i", [0] * SNOW_MOST * 5)
for flake in range(SNOW_MOST):
    FLAKES[flake * 5] = getrandbits(13)
    FLAKES[flake * 5 + 1] = getrandbits(13)
    FLAKES[flake * 5 + 2] = (0, 0, 1, 1, 2)[flake % 5]
    FLAKES[flake * 5 + 3] = 200 + getrandbits(7)
    FLAKES[flake * 5 + 4] = getrandbits(8)
# per layer: fall this frame in 1/64 px, pen strength. then drift in 1/64 px, sway phase, sway
# reach in px, colour, flakes to draw, a seed, and the layers to move and draw, first to last.
# then the shadow's colour, and the screen rows ink is on, from and to
SNOW_STATE = array("i", [0] * 12 + [0, 2, 0, 0, 0])
# a sine wave, 256 steps a turn, x256
SINE = array("i", [int(256 * math.sin(step * math.pi / 128)) for step in range(256)])


# ink is as for the rain
@micropython.viper
def snow(pixels: ptr32, flakes: ptr32, state: ptr32, sine: ptr32, ink: ptr32):  # noqa: F821
    side = int(state[6])
    spin = int(state[7])
    sway = int(state[8])
    colour = int(state[9])
    count = int(state[10])
    seed = int(state[11])
    snow_red = colour & 0xff
    snow_green = (colour >> 8) & 0xff
    snow_blue = (colour >> 16) & 0xff
    first = int(state[12])
    last = int(state[13])
    colour = int(state[14])
    shadow_red = colour & 0xff
    shadow_green = (colour >> 8) & 0xff
    shadow_blue = (colour >> 16) & 0xff
    ink_from = int(state[15])
    ink_to = int(state[16])
    flake = 0
    while flake < count:
        at = flake * 5
        layer = int(flakes[at + 2])
        if layer < first or layer > last:
            flake += 1
            continue
        y = int(flakes[at + 1]) + ((int(state[layer * 2]) * int(flakes[at + 3])) >> 8)
        x = int(flakes[at]) + side
        if y >= 130 << 6:
            seed = seed * 1664525 + 1013904223
            y = -(((seed >> 20) & 0xff) + 64)
            x = (seed >> 7) & 8191
        x &= 8191
        flakes[at] = x
        flakes[at + 1] = y
        row = y >> 6
        column = (x >> 6) + ((int(sine[(int(flakes[at + 4]) + spin) & 255]) * sway) >> 8)
        strength = int(state[layer * 2 + 1])
        # near flakes are bigger, a soft edged plus
        spots = 5 if layer == 2 else 1
        spot = 0
        while spot < spots:
            spot_row = row
            spot_column = column
            alpha = strength
            if spot > 0:
                alpha = strength >> 1
                if spot == 1:
                    spot_column += 1
                elif spot == 2:
                    spot_column -= 1
                elif spot == 3:
                    spot_row -= 1
                else:
                    spot_row += 1
            if spot_row >= 0 and spot_row < 128:
                spot_at = (spot_row << 7) | (spot_column & 127)
                under = int(pixels[spot_at])
                red = under & 0xff
                green = (under >> 8) & 0xff
                blue = (under >> 16) & 0xff
                if spot_row >= ink_from and spot_row < ink_to and green + CLOSE > snow_green and ((int(ink[spot_at - (ink_from << 7)]) >> 24) & 0xff) > 128:
                    pixels[spot_at] = OPAQUE | ((blue + (((shadow_blue - blue) * alpha) >> 8)) << 16) | ((green + (((shadow_green - green) * alpha) >> 8)) << 8) | (red + (((shadow_red - red) * alpha) >> 8))
                else:
                    pixels[spot_at] = OPAQUE | ((blue + (((snow_blue - blue) * alpha) >> 8)) << 16) | ((green + (((snow_green - green) * alpha) >> 8)) << 8) | (red + (((snow_red - red) * alpha) >> 8))
            spot += 1
        flake += 1
    state[11] = seed


# hail stones: x and y in 1/64 px, speed down in 1/64 px a second, the row it lands on and
# whether it has bounced
STONES = array("i", [0] * HAIL_STONES * 5)
for stone in range(HAIL_STONES):
    STONES[stone * 5] = getrandbits(13)
    STONES[stone * 5 + 1] = -randint(0, 200) << 6
    STONES[stone * 5 + 2] = randint(*HAIL_SPEED) << 6
# ms since the last frame, gravity in 1/64 px a second each ms, drift in 1/64 px this frame,
# the horizon, colour and a seed
HAIL_STATE = array("i", [0, (HAIL_GRAVITY << 6) // 1000, 0, HORIZON, 0, getrandbits(30)])


@micropython.viper
def hail(pixels: ptr32, stones: ptr32, state: ptr32):  # noqa: F821
    elapsed = int(state[0])
    gravity = int(state[1])
    side = int(state[2])
    horizon = int(state[3])
    colour = int(state[4])
    seed = int(state[5])
    hail_red = colour & 0xff
    hail_green = (colour >> 8) & 0xff
    hail_blue = (colour >> 16) & 0xff
    stone = 0
    while stone < HAIL_STONES:
        at = stone * 5
        x = int(stones[at]) + side
        y = int(stones[at + 1])
        speed = int(stones[at + 2]) + gravity * elapsed
        y += (speed * elapsed) // 1000
        floor = int(stones[at + 3])
        if floor == 0:
            # somewhere on the ground. near the horizon is far off, so most land there
            seed = seed * 1664525 + 1013904223
            spread = (seed >> 16) & 255
            floor = horizon + 3 + (((spread * spread) >> 8) * (124 - horizon)) // 255
            stones[at + 3] = floor
        if y >= floor << 6:
            if int(stones[at + 4]):
                # down again after its bounce: back to the top somewhere new
                seed = seed * 1664525 + 1013904223
                x = (seed >> 7) & 8191
                y = -(((seed >> 20) & 0xff) + 64) << 2
                speed = (70 + ((seed >> 4) & 31)) << 6
                stones[at + 3] = 0
                stones[at + 4] = 0
            else:
                y = floor << 6
                speed = -(speed * 3) // 10
                stones[at + 4] = 1
        x &= 8191
        stones[at] = x
        stones[at + 1] = y
        stones[at + 2] = speed
        row = y >> 6
        column = x >> 6
        # closer stones, landing lower down, look bigger
        spots = 4 if floor > horizon + 26 else 1
        spot = 0
        while spot < spots:
            spot_row = row + (spot >> 1)
            spot_column = (column + (spot & 1)) & 127
            alpha = 235 if spot == 0 else 150
            if spot_row >= 0 and spot_row < 128:
                spot_at = (spot_row << 7) | spot_column
                under = int(pixels[spot_at])
                red = under & 0xff
                green = (under >> 8) & 0xff
                blue = (under >> 16) & 0xff
                pixels[spot_at] = OPAQUE | ((blue + (((hail_blue - blue) * alpha) >> 8)) << 16) | ((green + (((hail_green - green) * alpha) >> 8)) << 8) | (red + (((hail_red - red) * alpha) >> 8))
            spot += 1
        stone += 1
    state[5] = seed


# how far the gusts' two swings and the flakes' sway have turned
gust_slow = 0.0
gust_fast = 0.0
swayed = 0.0


# the layers of rain and snow from this one on are near
NEAR_FROM = const(1)


# near: None for all the rain, snow and hail. False for only the far rain and snow, then True
# for the near with the hail, when something is drawn between them. the far come first in a
# frame, and that call sets how far it all moves. between is what was drawn between them, an
# image as wide as the screen, and top the screen row its first row is on: over its solid
# parts, near rain and snow that wouldn't show are drawn as shadows
def precipitation(w, t, near=None, between=None, top=0):  # noqa: ARG001
    global gust_slow, gust_fast, swayed
    if not (w["rain"] or w["snow"] or w["hail"]):
        return
    # a long frame would let things fall through each other
    step = min(dt, 0.1)
    day = clamp(w["day"])
    push = w["push"]
    pixels = memoryview(screen)
    first = NEAR_FROM if near else 0
    last = NEAR_FROM - 1 if near is False else 2
    ink = pixels
    ink_to = 0
    if near and between is not None:
        ink = memoryview(between)
        ink_to = top + between.height

    if w["rain"]:
        if not near:
            drops, layers = RAIN_LEVELS[min(int(w["rain"]), 3) - 1]
            # gusts swing the rain's slant back and forth
            gust_slow = (gust_slow + 0.47 * step) % (2 * math.pi)
            gust_fast = (gust_fast + 1.3 * step) % (2 * math.pi)
            gusting = max(0, w["gust"] - w["wind"]) * GUST_SLANT_PER_KMH * (0.5 + 0.5 * math.sin(gust_slow) * math.sin(gust_fast))
            slant = clamp(push * SLANT_PER_KMH + (gusting if push >= 0 else -gusting), -MOST_SLANT, MOST_SLANT)
            for layer in range(3):
                speed, length, strength = layers[layer]
                strength = int(strength * (0.6 + 0.4 * day))
                fall = speed * step * 64
                at = layer * 7
                RAIN_STEP[at] = int(fall)
                RAIN_STEP[at + 1] = int(fall * slant)
                RAIN_STEP[at + 2] = length
                RAIN_STEP[at + 3] = int(slant * 256)
                RAIN_STEP[at + 4] = strength
                RAIN_STEP[at + 5] = strength // (length + 1)
                RAIN_STEP[at + 6] = (128 + length) << 6
            RAIN_STATE[0] = drops
            colour = mix(RAIN_NIGHT, RAIN_DAY, day)
            RAIN_STATE[1] = pack(colour)
            RAIN_STATE[5] = pack(mix(colour, RAIN_SHADOW[0], RAIN_SHADOW[1]))
        RAIN_STATE[3] = first
        RAIN_STATE[4] = last
        RAIN_STATE[6] = top
        RAIN_STATE[7] = ink_to
        rain(pixels, DROPS, RAIN_STEP, RAIN_STATE, ink)

    if w["snow"]:
        if not near:
            for layer in range(3):
                speed, strength = SNOW_LAYERS[layer]
                SNOW_STATE[layer * 2] = int(speed * step * 64)
                SNOW_STATE[layer * 2 + 1] = strength
            SNOW_STATE[6] = int(clamp(push * SNOW_DRIFT_PER_KMH, -MOST_SNOW_DRIFT, MOST_SNOW_DRIFT) * step * 64)
            swayed = (swayed + 55 * step) % 256
            SNOW_STATE[7] = int(swayed)
            SNOW_STATE[8] = SNOW_SWAY
            colour = mix(SNOW_NIGHT, SNOW_DAY, day)
            SNOW_STATE[9] = pack(colour)
            SNOW_STATE[14] = pack(mix(colour, SNOW_SHADOW[0], SNOW_SHADOW[1]))
            SNOW_STATE[10] = SNOW_LEVELS[min(int(w["snow"]), 3) - 1]
        SNOW_STATE[12] = first
        SNOW_STATE[13] = last
        SNOW_STATE[15] = top
        SNOW_STATE[16] = ink_to
        snow(pixels, FLAKES, SNOW_STATE, SINE, ink)

    if w["hail"] and near is not False:
        HAIL_STATE[0] = int(step * 1000)
        HAIL_STATE[2] = int(push * 0.6 * step * 64)
        HAIL_STATE[3] = w.get("horizon", HORIZON)
        HAIL_STATE[4] = pack(mix(mix(RAIN_NIGHT, HAIL_PEN, 0.5), HAIL_PEN, day))
        hail(pixels, STONES, HAIL_STATE)


# --- lightning ---

# seconds to the next strike, and since the last
strike_in = None
since = 10.0
# the bolt as lines: from x, y to x, y, and how bright, 0-1
bolt = []
flash = 0.0


def make_bolt(horizon):
    lines = []
    x = uniform(24, 104)
    y = 12.0
    ground = horizon + randint(-2, 5)
    path = [(x, y)]
    while y < ground:
        x += uniform(-5, 5)
        y = min(ground, y + uniform(4, 8))
        path.append((x, y))
    for at in range(len(path) - 1):
        lines.append((path[at][0], path[at][1], path[at + 1][0], path[at + 1][1], 1.0))
    # a branch or two forking off, fading as they go
    for _ in range(randint(1, 2)):
        x, y = path[randint(1, max(1, len(path) // 2))]
        lean = uniform(3, 7) * (1 if getrandbits(1) else -1)
        for step in range(randint(3, 5)):
            to_x = x + lean + uniform(-2, 2)
            to_y = y + uniform(4, 7)
            lines.append((x, y, to_x, to_y, 0.55 - step * 0.1))
            x, y = to_x, to_y
    return lines


def flash_strength(since):
    for at in range(len(FLASH) - 1):
        start, strength = FLASH[at]
        end, next_strength = FLASH[at + 1]
        if start <= since < end:
            return strength + (next_strength - strength) * (since - start) / (end - start)
    return 0.0


def lightning(w, t):  # noqa: ARG001
    global strike_in, since, bolt, flash
    flash = 0.0
    if not w["storm"]:
        strike_in = None
        return
    if strike_in is None:
        strike_in = uniform(1, 3)
        since = 10.0
    strike_in -= dt
    since = min(since + dt, 10.0)
    if strike_in <= 0:
        strike_in = uniform(*STRIKE_GAP)
        since = 0.0
        bolt = make_bolt(w.get("horizon", HORIZON))
    flash = flash_strength(since)
    if flash <= 0:
        return
    screen.pen = pen(FLASH_PEN, 110 * flash)
    screen.rectangle(0, 0, 128, 128)
    if since < BOLT_SHOWS:
        for x1, y1, x2, y2, bright in bolt:
            screen.pen = pen(BOLT_GLOW, 130 * flash * bright)
            screen.line(x1 - 1, y1, x2 - 1, y2)
            screen.line(x1 + 1, y1, x2 + 1, y2)
            screen.pen = pen((255, 255, 255), 255 * min(1.0, flash * 1.4) * bright)
            screen.line(x1, y1, x2, y2)
