"""Rail Clock: the time inside two red rings whose chevrons sweep round.

The outer chevron goes round clockwise and the inner one anticlockwise, a turn
a minute each. They meet as the double arrow at the top on the minute, and
again at the bottom on the half minute.

The design follows Network Rail's Rail Clock (Design Bridge and Partners,
2025), as FireTVDeparture's clock tile draws it in a 200 unit square, scaled
here to fill the matrix. The time is in Inter Bold, whose tabular digits and
raised colon are packed in railclock_digits.af (SIL Open Font License 1.1, see
OFL-Inter.txt).

Only the chevrons move. The rings and the time are drawn into a face once a
minute, and a frame puts the face back in the boxes the chevrons covered before
drawing them again, the boxes looked up by the degree they've turned. The whole
face is copied in only when the firmware hands over a surface that doesn't hold
the last frame.
"""

import math
import time

import timezones
from plugin_config import plugin_config

HERE = __file__.rsplit("/", 1)[0]

# These values are exposed to the web interface
cfg = plugin_config("rail_clock", {
    "ring_colour": (208, 32, 47),  # the rings and chevrons, the board's red
    "time_colour": (236, 236, 236),  # the digits
    "background_colour": (0, 0, 0),  # black leaves the LEDs off
    "twelve_hour": False,  # 1:05 rather than 13:05
})
ring_colour = cfg["ring_colour"]
time_colour = cfg["time_colour"]
background_colour = cfg["background_colour"]
twelve_hour = cfg["twelve_hour"]

# renderRailClock(), in a 200 unit square: the rings' radii and stroke
OUTER = 82.0
INNER = 74.5
STROKE = 3.0
GAP = OUTER - INNER
MID = (OUTER + INNER) / 2.0
# the arms leave the ring at 27 degrees, as in Gerry Barney's logo
ARM = math.radians(27.0)
BACK = GAP / math.tan(ARM)
HALF = STROKE / 2.0 / math.sin(ARM)
SPAN = math.degrees(BACK / MID)
# the outer chevron's outward arm reaches furthest from the centre
REACH = OUTER + GAP

# the time: 34 units of Inter Bold, whose capitals stand 1490 of 2048. The
# packed font's stand 81/128 of the size it is drawn at
TIME_UNITS = 34.0
CAP = 81.0 / 128.0
CAP_RATIO = (1490.0 / 2048.0) / CAP

# px kept clear round the edge, one of which the frame hides
EDGE = 2

W, H = screen.width, screen.height
CX, CY = W / 2.0, H / 2.0
SCALE = (min(W, H) / 2.0 - EDGE) / REACH

SIZE = TIME_UNITS * SCALE * CAP_RATIO
INK = SIZE * CAP
# text() puts the baseline SIZE below the point it's given, so this centres the
# digits' ink on the face
TOP = CY - INK / 2.0 - (SIZE - INK)

# Left in the alpha byte of the face's top-left pixel, which the panel ignores.
# The firmware clears a surface to opaque black before handing it to a plugin
# that wasn't the last to draw there, so finding this on the surface means it
# still holds the frame drawn last.
MARK = 0x5A

ring_pen = color.rgb(*ring_colour)
time_pen = color.rgb(*time_colour)
background_pen = color.rgb(*background_colour)

# the firmware keeps a plugin's pen and so on with it from frame to frame, so
# the pen is only set again on a surface the clock hasn't drawn on
screen.antialias = image.X4
screen.pen = ring_pen

digits = font.load(HERE + "/railclock_digits.af")


def chevron(ring, tip, direction):
    """One chevron about the origin, railClockChevron() bent onto the rings, and
    its corners before it's turned.

    Built along the direction of travel and across the rings, so the arm
    crossing the gap ends on the other ring's centreline and the opposite arm
    mirrors it outward.
    """
    local = ((HALF, 0.0), (HALF - BACK, GAP), (-HALF - BACK, GAP), (-HALF, 0.0),
             (-HALF - BACK, -GAP), (HALF - BACK, -GAP))
    points = []
    for along, across in local:
        angle = math.radians(tip + direction * math.degrees(along / MID))
        radius = (ring + across) * SCALE
        points.append((radius * math.sin(angle), -radius * math.cos(angle)))

    return shape.custom([vec2(x, y) for x, y in points]), points


@micropython.native
def cover(boxes, corners, direction, degree):
    """The box on screen a chevron covers while turned between `degree` and the
    next, clockwise for direction 1. Worked out the first time it's needed."""
    box = boxes[degree]
    if box is None:
        xs, ys = [], []
        for turned in (degree, degree + 1):
            angle = math.radians(turned * direction)
            sine, cosine = math.sin(angle), math.cos(angle)
            for x, y in corners:
                xs.append(CX + x * cosine - y * sine)
                ys.append(CY + x * sine + y * cosine)
        # and a px round it for the antialiasing
        left, top = max(0, int(min(xs)) - 1), max(0, int(min(ys)) - 1)
        right, bottom = min(W, int(max(xs)) + 2), min(H, int(max(ys)) + 2)
        box = boxes[degree] = rect(left, top, right - left, bottom - top)
    return box


@micropython.native
def opaque(left, top, width, height):
    """Make the face opaque in a box: antialiasing leaves edges a shade short of
    it, and a box of the face blitted back has to replace what's there rather
    than blend with it."""
    for row in range(top, top + height):
        start = (row * W + left) * 4 + 3
        for alpha in range(start, start + width * 4, 4):
            face_pixels[alpha] = 255


# offset by half the chevron's span, so the two crossing arms coincide as the
# logo whenever the chevrons meet
outer, outer_corners = chevron(OUTER, SPAN / 2.0, 1)
inner, inner_corners = chevron(INNER, -SPAN / 2.0, -1)
# each chevron's box for each degree it turns
outer_boxes = [None] * 360
inner_boxes = [None] * 360

# Everything that isn't a chevron: the background, the rings and, once a
# minute, the time
face = image(W, H)
face.antialias = image.X4
face.font = digits
face.pen = background_pen
face.clear()
face.pen = ring_pen
for ring in (OUTER, INNER):
    face.shape(shape.arc(vec2(CX, CY), (ring - STROKE / 2.0) * SCALE, (ring + STROKE / 2.0) * SCALE, 0, 360))
face_pixels = memoryview(face)
opaque(0, 0, W, H)
face_pixels[3] = MARK

# Where any time goes, inside the inner ring: tabular digits make 00:00 as wide
# as any, and the box takes in the widest
widest = max(face.measure_text(text, font_size=SIZE)[0] for text in ("00:00", "--:--"))
TIME_BOX = (int(CX - widest / 2.0) - 2, int(TOP + SIZE - INK) - 2, int(widest) + 5, int(INK) + 5)
time_box = rect(*TIME_BOX)

# the time in the face, and the local minute it's for, as utc seconds
shown = None
minute_start = 0
minute_end = 0

# the surface drawn on last, its pixels, and the boxes to put back on it
surface = None
pixels = None
covered = ()

# the second of the minute the chevrons last saw tick over, and when
tick = None
tick_at = 0


def new_minute(now):
    """Find the local minute and draw its time into the face, adding the time's
    box to those to put back on screen if that changed it."""
    global shown, minute_start, minute_end, covered

    # off `now`, not a fresh look at the clock, or a second ticking over between
    # the two would put the chevrons a second out for the minute
    local = time.gmtime(now + timezones.utc_offset(now) * 60)
    # utc offsets are whole minutes, so local minutes start with utc ones
    minute_start = now - local[5]
    minute_end = minute_start + 60

    # the rtc starts in 2021 and keeps utc, so an earlier year is a clock ntp
    # hasn't set yet. the board shows --:-- until it has the time
    if local[0] < 2025:
        text = "--:--"
    elif twelve_hour:
        text = f"{local[3] % 12 or 12}:{local[4]:02d}"
    else:
        text = f"{local[3]:02d}:{local[4]:02d}"
    if text == shown:
        return
    shown = text

    face.pen = background_pen
    face.rectangle(time_box)
    face.pen = time_pen
    face.text(text, vec2(CX - face.measure_text(text, font_size=SIZE)[0] / 2.0, TOP), SIZE)
    opaque(*TIME_BOX)
    covered += (time_box,)


@micropython.native
def seconds(second):
    """The second of the minute with its fraction, off the ms since it ticked."""
    global tick, tick_at
    now = time.ticks_ms()
    # a second's gap means the plugin is back on screen, and its fraction unknown
    if second != tick or time.ticks_diff(now, tick_at) >= 1000:
        tick, tick_at = second, now
    return second + time.ticks_diff(now, tick_at) / 1000.0


@micropython.native
def update():
    global surface, pixels, covered

    now = time.time()
    # also when the clock is set back past the minute's start
    if not minute_start <= now < minute_end:
        new_minute(now)
    turned = seconds(now - minute_start) * 6.0

    if screen is not surface or pixels[3] != MARK:
        # a cleared surface, or another one: start again from the face
        surface, pixels = screen, memoryview(screen)
        pixels[:] = face_pixels
        screen.pen = ring_pen
    else:
        for box in covered:
            screen.blit(face, box, box)

    # the chevrons, a turn a minute each way
    outer.transform = mat3().translate(CX, CY).rotate(turned)
    inner.transform = mat3().translate(CX, CY).rotate(-turned)
    screen.shape(outer)
    screen.shape(inner)

    degree = int(turned) % 360
    covered = (cover(outer_boxes, outer_corners, 1, degree), cover(inner_boxes, inner_corners, -1, degree))
