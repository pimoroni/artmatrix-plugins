# the temperature blended into the weather scenes: big in the middle or smaller in a corner,
# in the scene's own light, with the weather passing behind it and in front. __init__ draws it after the land, the fog and
# the far rain and snow, then the near rain and snow over it, which sky.py shades where
# they cross the digits so they show.
#
# the digits are drawn once into a layer of their own, a little see-through, with a soft
# dark edge round them so they read over snow and sand. each frame the layer is put on the scene, a pixel at a time on the
# rows cloud or fog crosses, and less wherever those are in front. they're already on the
# screen by then, so a digit that keeps off them looks as if it's behind them. the high
# clouds of a fair day drift in front, the far ones low down stay behind. under a solid deck
# of cloud it's the ragged scud below it that crosses in front, and in fog its thicker banks.
# in a bottom corner __init__ draws it before the grass and the fog, so they cover it themselves
import micropython
from array import array

# the plugin's folder. the sky is loaded from it by path, as __init__ loads it and this
HERE = __name__.rsplit("/", 1)[0]
sky = __import__(HERE + "/sky")

# a pixel's alpha byte fully on, written signed for viper
OPAQUE = const(-16777216)

# Fredoka Bold's digits, minus and degree sign (SIL Open Font License 1.1, see
# OFL-Fredoka.txt). they stand 81/128 of the size they're drawn at, with the baseline that
# size below the point text() is given
FONT = font.load(HERE + "/temperature.af")
# how tall they stand in the middle, and in a corner, where they keep this far from the edges
INK = 36
SMALL = 22
MARGIN = 6
# further from the bottom, so the grass only reaches their feet
FOOT = 10
# the screen row the digits' middle is on in the middle. above the screen's, so their feet
# are near the horizon and their heads are among the clouds
MIDDLE = 47
# rows of the layer, the ink and the edge round it
ROWS = const(42)

# the digits' colour by night and by day, and how solid they are. a sunset turns them
# this colour by this much, and their feet take this much of the horizon's colour
NIGHT = (150, 164, 208)
DAY = (255, 255, 255)
SOLID = (195, 225)
SUNSET = ((255, 224, 188), 0.85)
FEET = 0.3
# the edge is the sky's colour, this much darkened, drawn at each of these offsets with
# these strengths, so it's soft. it's stronger under a bright sky, by up to this much
SHADE = 0.75
EDGE_AT = ((-1, -1, 30), (1, -1, 30), (-1, 1, 30), (1, 1, 30), (0, -1.5, 22), (0, 1.5, 22), (-1.5, 0, 22), (1.5, 0, 22),
           (0, 2.5, 16), (2.5, 0, 12), (-2.5, 0, 12))
BRIGHT_EDGE = 0.9

# how much of the digits each cover hides, by its alpha: none below the first, the most
# above the second. fair clouds, scud under a deck, and fog's banks
CLOUD = (30, 210, 205)
SCUD = (40, 200, 200)
FOG = (150, 250, 190)

LAYER = image(128, ROWS)
LAYER.antialias = image.X4
LAYER.font = FONT
CLEAR = bytes(128 * ROWS * 4)
# how much of each of the layer's pixels the digits cover, and each row's colour for them
INKED = bytearray(128 * ROWS)
FILLS = array("I", [0] * ROWS)
WHITE = color.rgb(255, 255, 255)
# for blend: the layer's rows to put on the screen, from and to, and its columns with ink
# in. then for each of two covers the screen rows it's on, from and to, the row its first
# is on and its column at the screen's left. then where the first cover's table is, the
# screen row the layer's first is on, and the tables: how much of the digits cloud, scud and
# fog hide at each alpha
COVER = const(4)
LAYER_TOP = const(13)
HIDES = const(16)
PARAMS = array("i", [0] * (HIDES + 768))
for table, (start, end, most) in enumerate((CLOUD, SCUD, FOG)):
    for alpha in range(256):
        amount = (alpha - start) / (end - start)
        PARAMS[HIDES + table * 256 + alpha] = int(most * (0 if amount < 0 else 1 if amount > 1 else amount))

# the change to the weather and the units the layer and covers were last worked out for,
# what the layer was drawn for, and the strips in front
seen = None
shown = None
drawn = None
covers = (None, None)

# where the digits stand, set by stand(): left, right or middle, whether that's along the
# bottom, how tall they are, the screen row the layer's first is on and the layer's row
# their heads are on
side = "middle"
low = False
ink_px = INK
top = 0
inside = 0


# stands the digits in the middle or a corner: centre, top-left, top-right, bottom-left
# or bottom-right. the layer's rows stay on the screen, with the digits as near the middle
# of them as that lets them be
def stand(where):
    global side, low, ink_px, top, inside, drawn
    side = "left" if where.endswith("left") else "right" if where.endswith("right") else "middle"
    low = where.startswith("bottom")
    ink_px = INK if side == "middle" else SMALL
    if side == "middle":
        head = MIDDLE - ink_px // 2
    elif low:
        head = 128 - FOOT - ink_px
    else:
        head = MARGIN
    top = min(128 - ROWS, max(0, head - (ROWS - ink_px) // 2))
    inside = head - top
    PARAMS[LAYER_TOP] = top
    drawn = None


stand("centre")


# how much of each pixel the digits cover, from the layer with them drawn on it in white
@micropython.viper
def cover(layer: ptr8, inked: ptr8):  # noqa: F821
    at = 0
    while at < 128 * ROWS:
        inked[at] = layer[(at << 2) + 3]
        at += 1


# puts the digits on the layer in each row's colour. the edge is already there, and stays
# only where they aren't, so it doesn't dull them. leaves the first and last columns with
# anything in for blend
@micropython.viper
def ink(layer: ptr32, inked: ptr8, fills: ptr32, params: ptr32):  # noqa: F821
    left = 128
    right = 0
    at = 0
    row = 0
    while row < ROWS:
        fill = int(fills[row])
        x = 0
        while x < 128:
            colour = int(layer[at])
            share = int(inked[at])
            if share:
                keep = 255 - share
                # red and blue together, then green and alpha
                colour = (((((colour & 0xff00ff) * keep + (fill & 0xff00ff) * share) >> 8) & 0xff00ff)
                          | ((((((colour >> 8) & 0xff00ff) * keep + ((fill >> 8) & 0xff00ff) * share) >> 8) & 0xff00ff) << 8))
                layer[at] = colour
            if colour:
                if x < left:
                    left = x
                if x >= right:
                    right = x + 1
            at += 1
            x += 1
        row += 1
    params[2] = left
    params[3] = right


# puts rows of the layer on the screen, less where a cover is in front. the layer's colours
# are already scaled by their alpha, and red and blue are worked out together
@micropython.viper
def blend(out: ptr32, layer: ptr32, params: ptr32, first: ptr32, second: ptr32):  # noqa: F821
    row = int(params[0])
    last = int(params[1])
    left = int(params[2])
    right = int(params[3])
    table = int(params[12])
    top = int(params[LAYER_TOP])
    while row < last:
        y = row + top
        first_at = -1
        if y >= int(params[4]) and y < int(params[5]):
            first_at = ((y - int(params[6])) << 8) + int(params[7])
        second_at = -1
        if y >= int(params[8]) and y < int(params[9]):
            second_at = ((y - int(params[10])) << 8) + int(params[11])
        source = row << 7
        spot = y << 7
        x = left
        while x < right:
            colour = int(layer[source + x])
            if colour:
                hide = 0
                if first_at >= 0:
                    hide = int(params[table + ((int(first[(first_at & -256) | ((first_at + x) & 255)]) >> 24) & 0xff)])
                if second_at >= 0:
                    hide += int(params[HIDES + 512 + ((int(second[(second_at & -256) | ((second_at + x) & 255)]) >> 24) & 0xff)])
                if hide < 250:
                    show = 256 - hide
                    keep = 255 - ((((colour >> 24) & 0xff) * show) >> 8)
                    under = int(out[spot + x])
                    out[spot + x] = (OPAQUE | ((((under & 0xff00ff) * keep + (colour & 0xff00ff) * show) >> 8) & 0xff00ff)
                                     | ((((under & 0xff00) * keep + (colour & 0xff00) * show) >> 8) & 0xff00))
            x += 1
        row += 1


# draws the layer for this label and light
def redraw(w, label):
    stops, warmth = sky.sky_colours(w)
    day = sky.clamp(w["day"])
    fill = sky.mix(sky.mix(NIGHT, DAY, day), SUNSET[0], warmth * SUNSET[1])
    feet = sky.mix(fill, stops[2], FEET)
    solid = SOLID[0] + (SOLID[1] - SOLID[0]) * day
    shade = sky.mix(stops[1], (0, 0, 0), SHADE)
    bright = 1 + BRIGHT_EDGE * (stops[1][0] * 0.3 + stops[1][1] * 0.6 + stops[1][2] * 0.1) / 255

    size = ink_px * 128 / 81
    width = LAYER.measure_text(label, size)[0]
    x = MARGIN if side == "left" else 128 - MARGIN - width if side == "right" else (128 - width) / 2
    y = inside - (size - ink_px)
    pixels = memoryview(LAYER)
    # the digits alone, for how much of each pixel they cover
    pixels[:] = CLEAR
    LAYER.pen = WHITE
    LAYER.text(label, vec2(x, y), size)
    cover(pixels, INKED)
    pixels[:] = CLEAR
    for across, down, strength in EDGE_AT:
        LAYER.pen = sky.pen(shade, strength * bright)
        LAYER.text(label, vec2(x + across, y + down), size)
    # the layer's colours are scaled by their alpha
    for row in range(ROWS):
        colour = sky.mix(fill, feet, sky.clamp(((row - inside) / ink_px - 0.45) / 0.55))
        FILLS[row] = (int(solid) << 24) | sky.pack(sky.mix((0, 0, 0), colour, solid / 255))
    ink(pixels, INKED, FILLS, PARAMS)


# where a cover is this frame, for blend, and the layer's rows it crosses, from and to. it's
# in front only once it's drawn and showing
def place(at, strip):
    if strip is None or not strip.shows:
        PARAMS[at] = PARAMS[at + 1] = 0
        return ROWS, 0
    start = strip.top + strip.first
    end = strip.top + strip.last
    PARAMS[at] = start
    PARAMS[at + 1] = end
    PARAMS[at + 2] = strip.top
    PARAMS[at + 3] = -int(strip.at) % 256
    return max(0, start - top), min(ROWS, end - top)


# the layer's rows from start to end, straight onto the screen
def stamp(start, end):
    left = PARAMS[2]
    across = PARAMS[3] - left
    if end > start:
        screen.blit(LAYER, rect(left, start, across, end - start), rect(left, top + start, across, end - start))


# the layer for this weather and these units, and which strips are in front
def plan(w, units):
    global drawn, covers
    degrees = w["temp"] * 9 / 5 + 32 if units == "fahrenheit" else w["temp"]
    # a real minus sign, as wide as a digit
    label = f"{round(degrees)}°".replace("-", "−")
    key = (label, sky.steps(w["day"], 16), sky.steps(w["dusk"], 8), w["sky"])
    if key != drawn:
        drawn = key
        redraw(w, label)
    deck = w["sky"] in sky.DECKS or w["storm"]
    PARAMS[12] = HIDES + 256 if deck else HIDES
    # along the bottom the fog is drawn over the digits, so it needn't hide them here
    covers = (sky.FAR if deck else sky.NEAR, sky.FOG if w["fog"] >= sky.FOG_EVEN and not low else None)


def draw(w, units):
    global seen, shown
    if w["change"] != seen or units != shown:
        seen = w["change"]
        shown = units
        plan(w, units)
    if PARAMS[3] <= PARAMS[2]:
        return
    start, end = place(COVER, covers[0])
    fog_start, fog_end = place(COVER + 4, covers[1])
    start = min(start, fog_start)
    end = max(end, fog_end)
    if start >= end:
        stamp(0, ROWS)
        return
    # only the rows a cover crosses need working out
    stamp(0, start)
    PARAMS[0] = start
    PARAMS[1] = end
    first = covers[0] or sky.NEAR
    second = covers[1] or sky.FOG
    blend(memoryview(screen), memoryview(LAYER), PARAMS, memoryview(first.image), memoryview(second.image))
    stamp(end, ROWS)
