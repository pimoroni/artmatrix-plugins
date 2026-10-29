import math
import random
import time

from plugin_config import plugin_config

SCHEMES = {
    # rim edge / part way / brightest / deep / rim line / glow
    "violet": ((102, 51, 255), (204, 68, 255), (255, 170, 238), (119, 34, 136), (204, 153, 255), (153, 68, 255)),
    "ember": ((230, 60, 30), (255, 140, 50), (255, 220, 140), (120, 20, 20), (255, 190, 80), (240, 90, 20)),
    "ice": ((60, 120, 210), (140, 200, 255), (230, 245, 255), (50, 40, 130), (200, 230, 255), (90, 160, 235)),
    "emerald": ((0, 160, 80), (0, 210, 120), (230, 255, 220), (20, 80, 20), (170, 255, 40), (0, 210, 120)),
}

# the mossy stone wall round the portal
STONE_SHADES = ((70, 74, 70), (84, 88, 82), (98, 102, 96), (112, 116, 108))
MORTAR = color.rgb(24, 28, 22)
MOSS = (60, 110, 40)

# stone sizes in px
COURSE = 10  # how tall a row of stones is
STONE_SHORTEST = 16
STONE_LONGEST = 26
ROW_OFFSET = 9  # every other row shifts left this far
ROW_SCATTER = 14  # and each row's start shifts left at random up to this far

cfg = plugin_config("magic_portal", {
    "scheme": "violet",  # one of SCHEMES
})
scheme = cfg["scheme"]

# unknown names fall back to the default so the config page ticks what's showing
if scheme not in SCHEMES:
    scheme = "violet"
EDGE, PART_WAY, BRIGHTEST, DEEP, RIM_LINE, RIM_GLOW = SCHEMES[scheme]

# from the rim (1) in to the opening (0). an arm darkens to black before the
# opening. a mote goes pale to white, then out
ARM_STOPS = ((1.0, EDGE), (0.65, PART_WAY), (0.4, BRIGHTEST), (0.2, DEEP), (0.0, (0, 0, 0)))
MOTE_STOPS = ((1.0, EDGE), (0.6, PART_WAY), (0.35, BRIGHTEST), (0.18, (255, 255, 255)), (0.0, (0, 0, 0)))

# the portal's movement
ARMS = 5
TURNS = 0.8  # how far round an arm winds from the rim to the opening
SPIN = 0.9  # how fast the arms turn, radians a second
MOTES = 40
FALL = 0.4  # how fast a mote falls, arm windings a second
MOTE_CURL = 0.4  # how far round a mote winds as it falls, of an arm's winding
OPENING = 0.34  # the dark opening's size, of the rim's

# how much of the last frame each frame dims away, of 255. more is shorter
# streaks. it's per frame, so tune it to the frame rate
DIM = 50

# longest step in seconds. coming back from another plugin carries on rather
# than jumping
LONGEST_STEP = 0.1

# sizes in px
GLOW_WIDTH = 5  # an arm's glow at the rim, narrowing toward the opening
CORE_WIDTH = 1.5  # its bright core
RIM_WIDTH = 1.5  # the rim's bright line
MOTE_WIDTH = 1.5  # a mote's streak at the rim
BAND = 9  # how deep the ring of stones round the rim is
EDGE_GAP = 2  # between the ring of stones and the panel's edge
ARM_GAP = 2  # between an arm's glow and the rim

# detail
POINTS = 30  # steps along an arm from the rim in
# an arm is drawn in this many pieces, a colour each. POINTS must divide by it
LENGTHS = 5
RIM_STEPS = 48  # points round the rim
RIM_SHAKE = 0.04  # how far in a rim point strays each frame, of the rim's size
RING_STONES = 20  # stones in the ring round the rim
MOTE_SHADES = 50  # steps in a mote's colours from the opening out
GLOW_ALPHA = 70  # how strong an arm's glow is, of 255
RIM_GLOW_ALPHA = 90

# toward the opening an arm thins by up to this share of its width at the rim
GLOW_NARROWING = 0.7
CORE_NARROWING = 0.6

# how much lighter a stone's top and left edges are. its bottom and right are
# darker by the same
STONE_LIGHT = 34

# how much lighter or darker a fleck on a stone is
FLECK_SHADES = (-17, -34, 17)

# the portal's light on the stones: how far out from the rim in px, and how
# strong, of 255
SPILL = ((2, 70), (5, 40), (8, 22))

MIDDLE_X = screen.width / 2
MIDDLE_Y = screen.height / 2
ORIGIN = vec2(0, 0)

# the rim is as large as fits inside the ring of stones
OUTER = MIDDLE_Y - BAND - EDGE_GAP
INNER = OUTER * OPENING
BETWEEN_ARMS = 2 * math.pi / ARMS
WINDING = TURNS * 2 * math.pi
ARM_OUTER = OUTER - GLOW_WIDTH / 2 - ARM_GAP
# where the rim's line sits, its glow reaching the edge
RIM_LINE_OUTER = OUTER - RIM_WIDTH * 1.5

# an arm is a log spiral. it shrinks by the same share every step round, so it
# winds evenly from just inside the rim to the opening
SHRINK = math.log(ARM_OUTER / INNER) / WINDING

OPEN_PATH = shape.ALIGN_CENTER | shape.PATH_OPEN


# the colour this far out from the opening, 1 at the rim to 0 at the opening
def colour_at(stops, reach):
    for (high, high_rgb), (low, low_rgb) in zip(stops, stops[1:]):
        if reach >= low:
            part = (reach - low) / (high - low)
            return tuple(round(lower + (higher - lower) * part) for higher, lower in zip(high_rgb, low_rgb))
    return stops[-1][1]


# the point at an angle and a distance out from the middle
def placed(angle, distance):
    return vec2(MIDDLE_X + distance * math.cos(angle), MIDDLE_Y + distance * math.sin(angle))


# a pen for a colour lightened or darkened by a step
def shade(rgb, by):
    return color.rgb(*(max(0, min(255, channel + by)) for channel in rgb))


# the first arm from the rim in, centred on 0,0. every arm is this one turned
spiral = []
for step in range(POINTS + 1):
    angle = WINDING * step / POINTS
    distance = ARM_OUTER * math.exp(-SHRINK * angle)
    spiral.append(vec2(distance * math.cos(angle), distance * math.sin(angle)))

# per piece of an arm: glow pen, glow, core pen, core. built once and turned
# by their transform. the colour is taken at the piece's middle, and both
# narrow toward the opening
PER_LENGTH = POINTS // LENGTHS
PIECES = []
for length in range(LENGTHS):
    red, green, blue = colour_at(ARM_STOPS, 1 - (length + 0.5) / LENGTHS)
    narrowing = length / LENGTHS
    points = spiral[length * PER_LENGTH:(length + 1) * PER_LENGTH + 1]
    glow = shape.custom(points).stroke(GLOW_WIDTH * (1 - GLOW_NARROWING * narrowing), OPEN_PATH)
    core = shape.custom(points).stroke(CORE_WIDTH * (1 - CORE_NARROWING * narrowing), OPEN_PATH)
    PIECES.append((color.rgb(red, green, blue, GLOW_ALPHA), glow, color.rgb(red, green, blue), core))

# a mote's pen at each step out from the opening. one at the rim starts four
# fifths along its colours, already lit, so it shows against the arms
MOTE_PENS = [color.rgb(*colour_at(MOTE_STOPS, 0.8 * step / MOTE_SHADES)) for step in range(MOTE_SHADES + 1)]

RIM_DIRECTIONS = [(math.cos(2 * math.pi * step / RIM_STEPS), math.sin(2 * math.pi * step / RIM_STEPS))
                  for step in range(RIM_STEPS)]
RIM_LINE_PEN = color.rgb(*RIM_LINE)
RIM_GLOW_PEN = color.rgb(*RIM_GLOW, RIM_GLOW_ALPHA)
DIM_PEN = color.rgb(0, 0, 0, DIM)
OPENING_SHAPE = shape.circle(MIDDLE_X, MIDDLE_Y, OUTER)

# the wall, drawn once: rows of stones, each row offset from the last, then a
# ring of stones round the rim and the portal's light on them
WALL = image(screen.width, screen.height)
WALL.pen = MORTAR
WALL.clear()
for row, top in enumerate(range(-2, screen.height, COURSE)):
    x = -random.randint(0, ROW_SCATTER) - (ROW_OFFSET if row % 2 else 0)
    while x < screen.width:
        width = random.randint(STONE_SHORTEST, STONE_LONGEST)
        base = random.choice(STONE_SHADES)
        left, right, upper, lower = x + 1, x + width - 1, top + 1, top + COURSE - 1

        # lit along the top and left, shaded along the bottom and right, then
        # a few flecks
        WALL.pen = shade(base, -STONE_LIGHT)
        WALL.rectangle(rect(left, upper, right - left, lower - upper))
        WALL.pen = shade(base, STONE_LIGHT)
        WALL.rectangle(rect(left, upper, right - left - 1, lower - upper - 1))
        WALL.pen = color.rgb(*base)
        WALL.rectangle(rect(left + 1, upper + 1, right - left - 2, lower - upper - 2))
        for _ in range(2):
            fleck_x = random.randint(left + 2, right - 3)
            fleck_y = random.randint(upper + 2, lower - 3)
            WALL.pen = shade(base, random.choice(FLECK_SHADES))
            WALL.rectangle(rect(fleck_x, fleck_y, 1, 1))

        # moss creeping along the top of about half the stones
        if random.getrandbits(1):
            moss_width = random.randint(3, 6)
            moss_height = random.randint(1, 2)
            moss_left = random.randint(left, right - moss_width)
            WALL.pen = shade(MOSS, random.choice((-17, 0, 17)))
            WALL.rectangle(rect(moss_left, upper, moss_width, moss_height))
        x += width

WALL.pen = MORTAR
WALL.shape(shape.circle(MIDDLE_X, MIDDLE_Y, OUTER + BAND + 1))
WALL.antialias = image.X4
for stone in range(RING_STONES):
    # a small gap either side of each stone for the mortar to show through
    first = 2 * math.pi * (stone - 0.5) / RING_STONES - math.pi / 2 + 0.02
    last = 2 * math.pi * (stone + 0.5) / RING_STONES - math.pi / 2 - 0.02
    inner = [placed(first + (last - first) * part / 4, OUTER) for part in range(5)]
    outer = [placed(last - (last - first) * part / 4, OUTER + BAND) for part in range(5)]
    base = random.choice(STONE_SHADES)
    WALL.pen = color.rgb(*base)
    WALL.shape(shape.custom(inner + outer))
    WALL.pen = shade(base, -STONE_LIGHT)
    WALL.shape(shape.custom(outer).stroke(1, OPEN_PATH))
    WALL.pen = shade(base, STONE_LIGHT)
    WALL.shape(shape.custom(inner).stroke(1, OPEN_PATH))
    fleck = placed(random.uniform(first + 0.05, last - 0.05), OUTER + random.uniform(2, BAND - 2))
    WALL.pen = shade(MOSS, random.choice(FLECK_SHADES))
    WALL.rectangle(rect(int(fleck.x), int(fleck.y), 1, 1))

for reach, strength in SPILL:
    WALL.pen = color.rgb(*RIM_GLOW, strength)
    WALL.shape(shape.circle(MIDDLE_X, MIDDLE_Y, OUTER + reach / 2).stroke(reach, shape.ALIGN_CENTER))

# the opening, kept between frames so the motes leave fading streaks. clear
# outside the rim so the wall shows round it
PORTAL = image(screen.width, screen.height)
PORTAL.pen = color.rgb(0, 0, 0, 0)
PORTAL.clear()
PORTAL.antialias = image.X4
PORTAL.pen = color.black
PORTAL.shape(OPENING_SHAPE)


# per mote: the angle it starts at, and how far it has fallen in radians of an
# arm's winding. spread out at first, then each restarts at the rim
mote_homes = [random.uniform(0, 2 * math.pi) for _ in range(MOTES)]
mote_fallen = [random.uniform(0, WINDING * 0.9) for _ in range(MOTES)]

# where each mote was last frame. None until it has been placed once, so
# there's nothing to streak from
mote_was = [None] * MOTES

# how far the arms have turned, wrapping at the angle between two arms
spun = 0.0
last = time.ticks_ms()


def update():
    global spun, last

    now = time.ticks_ms()
    seconds = min(LONGEST_STEP, time.ticks_diff(now, last) / 1000)
    last = now
    spun = (spun + SPIN * seconds) % BETWEEN_ARMS

    PORTAL.pen = DIM_PEN
    PORTAL.shape(OPENING_SHAPE)

    for arm in range(ARMS):
        # one matrix shared by every piece of the arm. the transform setter copies it
        turned = mat3().translate(MIDDLE_X, MIDDLE_Y).rotate(math.degrees(spun + arm * BETWEEN_ARMS))
        for glow_pen, glow, core_pen, core in PIECES:
            glow.transform = turned
            core.transform = turned
            # the glow is wide and faint so a rough edge never shows. only the core is smoothed
            PORTAL.antialias = image.OFF
            PORTAL.pen = glow_pen
            PORTAL.shape(glow)
            PORTAL.antialias = image.X4
            PORTAL.pen = core_pen
            PORTAL.shape(core)

    for mote in range(MOTES):
        mote_fallen[mote] += FALL * WINDING * seconds
        if mote_fallen[mote] > WINDING:
            mote_homes[mote] = random.uniform(0, 2 * math.pi)
            mote_fallen[mote] = random.uniform(0, 0.3)
            mote_was[mote] = None
            continue

        distance = ARM_OUTER * math.exp(-SHRINK * mote_fallen[mote])
        was = mote_was[mote]
        now_at = placed(mote_homes[mote] + MOTE_CURL * mote_fallen[mote], distance)
        mote_was[mote] = now_at
        if was is None:
            continue
        reach = max(0, (distance - INNER) / (ARM_OUTER - INNER))
        PORTAL.pen = MOTE_PENS[round(reach * MOTE_SHADES)]
        # a streak narrows as it falls, to a floor that still shows
        PORTAL.shape(shape.line(was.x, was.y, now_at.x, now_at.y, MOTE_WIDTH * max(0.4, distance / OUTER)))

    screen.blit(WALL, ORIGIN)
    screen.blit(PORTAL, ORIGIN)

    # the rim: each point strays in at random, smoothed with its neighbours
    strays = [random.random() for _ in range(RIM_STEPS)]
    rim = []
    for step, (across, down) in enumerate(RIM_DIRECTIONS):
        stray = (strays[step - 1] + strays[step] + strays[(step + 1) % RIM_STEPS]) / 3
        distance = RIM_LINE_OUTER * (1 - RIM_SHAKE * stray)
        rim.append(vec2(MIDDLE_X + distance * across, MIDDLE_Y + distance * down))

    # stroke() replaces the shape with its outline, so each stroke needs its own
    screen.antialias = image.OFF
    screen.pen = RIM_GLOW_PEN
    screen.shape(shape.custom(rim).stroke(RIM_WIDTH * 3, shape.ALIGN_CENTER))
    screen.antialias = image.X4
    screen.pen = RIM_LINE_PEN
    screen.shape(shape.custom(rim).stroke(RIM_WIDTH, shape.ALIGN_CENTER))
