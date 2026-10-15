import math
import time
import micropython
from array import array
from random import uniform

from plugin_config import plugin_config

cfg = plugin_config("cells", {
    "pace": 2,  # 1 slow, 2 steady, 3 busy
    "dish": 6,  # the most cells at once: 4, 6 or 8
    "nucleus": 1,  # 1 to show the nucleus, 0 to hide it
    "theme": "mono",  # mono, glow, violet, plankton or agar
})
pace = cfg["pace"]
dish = cfg["dish"]
nucleus = cfg["nucleus"]
theme = cfg["theme"]

# (rim colour, stops): cells add 1024 at the centre to 0 at the edge, the total picks a stop
SCHEMES = {
    # phase contrast: dark shadow, bright membrane, dark inside
    "mono": ((120, 120, 120), [
        (0, (190, 190, 190)),
        (60, (170, 170, 170)),
        (200, (90, 90, 90)),
        (285, (45, 45, 45)),
        (300, (225, 225, 225)),
        (420, (225, 225, 225)),
        (460, (110, 110, 110)),
        (840, (60, 60, 60)),
        (850, (30, 30, 30)),
        (1023, (20, 20, 20)),
    ]),
    # green glow on a navy dish, red nucleus
    "glow": ((24, 6, 40), [
        (0, (6, 26, 90)),
        (60, (8, 40, 90)),
        (200, (20, 100, 70)),
        (290, (60, 170, 60)),
        (305, (170, 255, 90)),
        (360, (150, 235, 80)),
        (390, (80, 190, 60)),
        (840, (50, 150, 45)),
        (850, (200, 20, 30)),
        (900, (240, 40, 40)),
        (1023, (255, 110, 90)),
    ]),
    # crystal violet, gold nucleus
    "violet": ((20, 4, 34), [
        (0, (50, 15, 100)),
        (60, (60, 20, 110)),
        (200, (100, 40, 150)),
        (290, (150, 70, 200)),
        (305, (235, 170, 255)),
        (360, (215, 140, 255)),
        (390, (150, 70, 210)),
        (840, (115, 45, 175)),
        (850, (255, 170, 30)),
        (900, (255, 200, 60)),
        (1023, (255, 235, 140)),
    ]),
    # teal sea, coral nucleus
    "plankton": ((0, 14, 22), [
        (0, (0, 55, 75)),
        (60, (0, 65, 85)),
        (200, (10, 110, 120)),
        (290, (40, 170, 160)),
        (305, (150, 255, 230)),
        (360, (120, 240, 215)),
        (390, (40, 180, 165)),
        (840, (25, 140, 135)),
        (850, (255, 100, 40)),
        (900, (255, 130, 60)),
        (1023, (255, 190, 120)),
    ]),
    # colonies on amber agar
    "agar": ((50, 20, 2), [
        (0, (150, 80, 10)),
        (60, (160, 90, 15)),
        (200, (190, 130, 40)),
        (290, (220, 170, 70)),
        (305, (255, 235, 160)),
        (360, (250, 225, 150)),
        (390, (235, 200, 110)),
        (840, (225, 180, 90)),
        (850, (180, 90, 20)),
        (900, (150, 65, 15)),
        (1023, (110, 45, 10)),
    ]),
}
RIM, STOPS = SCHEMES.get(theme, SCHEMES["mono"])
if not nucleus:
    # inside colour runs on to the centre
    STOPS = [s for s in STOPS if s[0] < 850]
    STOPS.append((1023, STOPS[-1][1]))

COLOURS = [None] * 1024
for s in range(len(STOPS) - 1):
    lo, a = STOPS[s]
    hi, b = STOPS[s + 1]
    for i in range(lo, hi + 1):
        f = (i - lo) / (hi - lo)
        COLOURS[i] = (
            int(a[0] + (b[0] - a[0]) * f),
            int(a[1] + (b[1] - a[1]) * f),
            int(a[2] + (b[2] - a[2]) * f),
        )

# 8 tables, one per light level. only dish and glow (below 300) dim towards RIM
PALETTE = array("I", [0] * 8 * 1024)
same = memoryview(PALETTE)
for level in range(8):
    o = level * 1024
    for i in range(300):
        r, g, b = COLOURS[i]
        # blend from RIM, more with glow strength and light level
        k = i * 256 // 300
        k += (256 - k) * level // 7
        r = RIM[0] + (r - RIM[0]) * k // 256
        g = RIM[1] + (g - RIM[1]) * k // 256
        b = RIM[2] + (b - RIM[2]) * k // 256
        PALETTE[o + i] = 0xff000000 | (b << 16) | (g << 8) | r
    if level == 0:
        for i in range(300, 1024):
            r, g, b = COLOURS[i]
            PALETTE[i] = 0xff000000 | (b << 16) | (g << 8) | r
    else:
        same[o + 300:o + 1024] = same[300:1024]

# light x16 by squared distance (half px) / 32, so no sqrt per pixel
LEVEL = bytearray(1009)
for j in range(1009):
    t = min(max((66 - math.sqrt(j << 5) / 2) / 36, 0), 1)
    LEVEL[j] = int(t * t * (3 - 2 * t) * 7 * 16)

# light per pixel, dithered so the fade shows no rings
DITHER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
DX2 = [(2 * x - 127) ** 2 for x in range(128)]
LIGHT = bytearray(128 * 128)
i = 0
for y in range(128):
    dy2 = (2 * y - 127) ** 2
    dither = DITHER[(y & 3) * 4:(y & 3) * 4 + 4]
    for x in range(128):
        LIGHT[i] = (LEVEL[(DX2[x] + dy2) >> 5] + dither[x & 3]) >> 4
        i += 1

# grown membrane radius, sized so a full dish fills the panel
FULL = {4: 24, 6: 20, 8: 17}.get(dish, 20)
NEWBORN = FULL * 0.7071  # half the area of a grown cell
REACH = 1.48  # push reach vs membrane
GROW = 10 / pace  # seconds from newborn to full size
FADE = 0.5  # seconds to fade a cell in or a mother out
SPREAD = 0.5  # seconds for daughters to slow after a split
SETTLE = 1.5  # seconds before daughters get pushed apart
HOLD = 4  # seconds a full dish holds
EMPTY = 1.5  # seconds to fade a full dish out

# count first, then 6 per cell. x and y in 16ths of a px. reach, reach squared, closeness
# scale, strength 0-256. one spare slot for a fading mother
BALLS = array("i", [0] * (1 + (dish + 1) * 6))


# builds each row in the screen itself: light level in the top bits (<< 20), cells add below
@micropython.viper
def draw_cells(pixels: ptr32, pal: ptr32, balls: ptr32, light: ptr8):  # noqa: F821
    balls_end = 1 + int(balls[0]) * 6
    y = 0
    while y < 128:
        row = y << 7
        x = 0
        while x < 128:
            pixels[row + x] = int(light[row + x]) << 20
            x += 1

        spot_y = (y << 4) + 8
        ball = 1
        while ball < balls_end:
            ball_x = int(balls[ball])
            reach = int(balls[ball + 2])
            down = spot_y - int(balls[ball + 1])
            room_left = int(balls[ball + 3]) - down * down
            if room_left > 0:
                closeness_scale = int(balls[ball + 4])
                strength = int(balls[ball + 5])
                x = (ball_x - reach) >> 4
                if x < 0:
                    x = 0
                last_x = (ball_x + reach) >> 4
                if last_x > 127:
                    last_x = 127
                while x <= last_x:
                    across = (x << 4) + 8 - ball_x
                    inside = room_left - across * across
                    if inside > 0:
                        # 0 at the edge of its reach, 256 at the centre
                        closeness = (inside * closeness_scale) >> 20
                        pixels[row + x] += (closeness * closeness * strength) >> 14
                    x += 1
            ball += 6

        x = 0
        while x < 128:
            packed = int(pixels[row + x])
            total = packed & 0xfffff
            if total > 1023:
                total = 1023
            pixels[row + x] = pal[((packed >> 20) << 10) + total]
            x += 1
        y += 1


class Cell:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        a = uniform(0, 2 * math.pi)
        speed = uniform(2, 4)
        self.drift_x = math.cos(a) * speed
        self.drift_y = math.sin(a) * speed
        self.vx = self.drift_x
        self.vy = self.drift_y
        self.size = NEWBORN
        self.fade = 0
        self.age = 0


cells = []
mother = None  # the cell that just split, fading out
holding = 0  # seconds left showing a full dish
emptying = False
last = time.ticks_ms()


def start_dish():
    global cells, emptying
    cells = [Cell(uniform(40, 88), uniform(40, 88))]
    emptying = False


start_dish()


def update():
    global mother, holding, emptying, last

    t = time.ticks_ms()
    # long gap means we were away, don't jump ahead
    dt = min(time.ticks_diff(t, last), 100) / 1000
    last = t

    for c in cells:
        c.age += dt
        if emptying:
            c.fade = max(0, c.fade - dt / EMPTY)
        else:
            c.fade = min(1, c.fade + dt / FADE)
        c.size = min(FULL, c.size + (FULL - NEWBORN) * dt / GROW)

        # daughters start fast and ease down to a wander
        ease = min(1, dt / SPREAD)
        c.vx += (c.drift_x - c.vx) * ease
        c.vy += (c.drift_y - c.vy) * ease
        c.x += c.vx * dt
        c.y += c.vy * dt

        # bounce while most of the cell's still showing
        edge = c.size * 0.7
        if c.x < edge or c.x > 128 - edge:
            c.x = min(max(c.x, edge), 128 - edge)
            c.drift_x = -c.drift_x
            c.vx = -c.vx
        if c.y < edge or c.y > 128 - edge:
            c.y = min(max(c.y, edge), 128 - edge)
            c.drift_y = -c.drift_y
            c.vy = -c.vy

    # nudge settled cells apart so a full dish doesn't clump
    for i in range(len(cells)):
        a = cells[i]
        if a.age < SETTLE:
            continue
        for b in cells[i + 1:]:
            if b.age < SETTLE:
                continue
            dx = b.x - a.x
            dy = b.y - a.y
            gap = a.size + b.size + 3
            d2 = dx * dx + dy * dy
            if 0 < d2 < gap * gap:
                d = math.sqrt(d2)
                move = (gap - d) * min(1, dt * 2) / 2 / d
                a.x -= dx * move
                a.y -= dy * move
                b.x += dx * move
                b.y += dy * move

    if mother:
        mother.fade -= dt / FADE
        if mother.fade <= 0:
            mother = None

    if emptying:
        if all(c.fade == 0 for c in cells):
            start_dish()
    elif holding:
        holding = max(0, holding - dt)
        emptying = holding == 0
    elif len(cells) >= dish:
        if mother is None and all(c.size == FULL for c in cells):
            holding = HOLD
    elif mother is None:
        # one split at a time, first grown cell goes
        for c in cells:
            if c.size == FULL:
                a = uniform(0, 2 * math.pi)
                # daughters shoot ~1.25 newborn sizes, then wander
                push = NEWBORN * 1.25 / SPREAD
                for side in (1, -1):
                    d = Cell(c.x, c.y)
                    d.vx = c.vx + math.cos(a) * push * side
                    d.vy = c.vy + math.sin(a) * push * side
                    cells.append(d)
                cells.remove(c)
                mother = c
                break

    n = 0
    for c in cells + [mother] if mother else cells:
        o = 1 + n * 6
        r = int(c.size * REACH * 16)
        BALLS[o] = int(c.x * 16)
        BALLS[o + 1] = int(c.y * 16)
        BALLS[o + 2] = r
        BALLS[o + 3] = r * r
        BALLS[o + 4] = (256 << 20) // (r * r)
        BALLS[o + 5] = int(c.fade * 256)
        n += 1
    BALLS[0] = n

    draw_cells(memoryview(screen), PALETTE, BALLS, LIGHT)
