import math
import time
from random import getrandbits

from plugin_config import plugin_config

# a flip dot display. each disc is yellow on one side, black on the other. it
# flips over when the pattern needs its other face.
#
# a flip takes a few frames: the disc narrows to its edge, then widens showing
# the other face. the columns start a moment apart, as a real panel's driver
# sweeps across them. the discs turn on a diagonal axle.
#
# it shows one pattern, or all of them taking turns
cfg = plugin_config("flipdots", {
    "pattern": "cycle",  # cycle, or one of PATTERNS
})
pattern = cfg["pattern"]

# dots across and down, px from one to the next, where the first one is and a
# disc's radius
COLUMNS = 21
ROWS = 21
PITCH = 6
LEFT = 1
TOP = 1
RADIUS = 2.4
# a disc's offset from its square's middle, right and down
NUDGE = -0.5
# the middle dot, across and down
MIDDLE = (COLUMNS - 1) / 2

# frames a flip takes and ms each shows for, then ms between one column
# starting and the next
TURN = 16
FRAME = 20
SWEEP = 3

# the backing, and a disc's yellow and black faces
BACKING = (5, 5, 5)
YELLOW = (250, 222, 40)
BLACK = (30, 30, 28)

# ms between a pattern's steps, and ms each pattern shows for when they take turns
STEP = 125
SHOW = 20000


# a disc frame frames into flipping from black to yellow, on a PITCH px square
def disc(frame):
    square = image(PITCH, PITCH)
    square.antialias = image.X4
    square.pen = color.rgb(*BACKING)
    square.clear()
    # 1 face on, 0 edge on
    width = abs(math.cos(math.pi * frame / TURN))
    face = YELLOW if 2 * frame > TURN else BLACK
    square.pen = color.rgb(*face)
    middle = PITCH / 2 + NUDGE
    outline = shape.circle(middle, middle, RADIUS)
    # squashed across the diagonal axle, never quite flat so the edge still shows
    outline.transform = (mat3().translate(middle, middle).rotate(45).scale(max(width, 0.15), 1)
                         .rotate(-45).translate(-middle, -middle))
    square.shape(outline)
    return square


# one image per frame of a flip
DISCS = [disc(frame) for frame in range(TURN + 1)]

# per dot: frames turned toward yellow (0 black, TURN yellow), the face it
# should end on and the face the flip it's in ends on. due is the tick it next
# moves on. moving holds the dots mid flip
turned = bytearray(COLUMNS * ROWS)
wanted = bytearray(COLUMNS * ROWS)
heading = bytearray(COLUMNS * ROWS)
due = [0] * (COLUMNS * ROWS)
moving = set()

# every disc as it is now. only the ones that move are drawn again
board = image(screen.width, screen.height)
board.pen = color.rgb(*BACKING)
board.clear()
for i in range(COLUMNS * ROWS):
    board.blit(DISCS[0], LEFT + i % COLUMNS * PITCH, TOP + i // COLUMNS * PITCH)


# sets the face each dot should end on, and starts the ones that need to flip
def want(dots, now):
    for i in range(COLUMNS * ROWS):
        target = TURN if dots[i] else 0
        if wanted[i] != target:
            wanted[i] = target
            if i not in moving:
                moving.add(i)
                due[i] = time.ticks_add(now, i % COLUMNS * SWEEP)


# moves each flipping dot on a frame. a flip always finishes on the other face,
# as a disc can't stop halfway. if the dot's wanted back it flips again after
def turn(now):
    for i in list(moving):
        if time.ticks_diff(now, due[i]) < 0:
            continue
        frame = turned[i]
        if frame == 0 or frame == TURN:
            if wanted[i] == frame:
                moving.discard(i)
                continue
            heading[i] = wanted[i]
        frame += 1 if heading[i] > frame else -1
        turned[i] = frame
        board.blit(DISCS[frame], LEFT + i % COLUMNS * PITCH, TOP + i // COLUMNS * PITCH)
        due[i] = time.ticks_add(due[i], FRAME)
        if frame == heading[i] == wanted[i]:
            moving.discard(i)


# the patterns. each takes a step number and returns which dots are yellow.
# step 0 is a pattern's first, and the ones that keep state start afresh on it

def waves(step):
    phase = step * 0.12
    dots = bytearray(COLUMNS * ROWS)
    for y in range(ROWS):
        for x in range(COLUMNS):
            height = math.sin(x * 0.45 + phase) + math.sin(y * 0.38 - phase * 1.3) + math.sin((x + y) * 0.27 + phase * 0.7)
            dots[y * COLUMNS + x] = height > 0.3
    return dots


def rings(step):
    # the middle wanders slowly round the panel
    centre_x = MIDDLE + MIDDLE * 0.6 * math.sin(step * 0.03)
    centre_y = MIDDLE + MIDDLE * 0.6 * math.cos(step * 0.041)
    dots = bytearray(COLUMNS * ROWS)
    for y in range(ROWS):
        for x in range(COLUMNS):
            distance = math.sqrt((x - centre_x) ** 2 + (y - centre_y) ** 2)
            dots[y * COLUMNS + x] = (distance - step * 0.5) % 6 < 2.5
    return dots


# the live cells, and the last few generations so a loop can be spotted
life = bytearray(COLUMNS * ROWS)
life_seen = []


def game_of_life(step):
    global life, life_seen
    # a fresh random board at the start, when everything's died, or when it's stuck in a loop
    if step == 0 or not any(life) or life in life_seen:
        life = bytearray(getrandbits(2) == 0 for _ in range(COLUMNS * ROWS))
        life_seen = []
    # a new generation every other step
    if step % 2:
        return life
    life_seen = (life_seen + [life])[-6:]
    dots = bytearray(COLUMNS * ROWS)
    for y in range(ROWS):
        for x in range(COLUMNS):
            around = 0
            for offset_y in (-1, 0, 1):
                for offset_x in (-1, 0, 1):
                    if offset_x or offset_y:
                        around += life[(y + offset_y) % ROWS * COLUMNS + (x + offset_x) % COLUMNS]
            dots[y * COLUMNS + x] = around == 3 or (around == 2 and life[y * COLUMNS + x])
    life = dots
    return dots


# the drops falling as [column, row of the head, length], and the column the
# last one started in. -2 lets the first start anywhere
drops = []
last_drop = -2


def rain(step):
    global drops, last_drop
    if step == 0:
        drops = []
    # a new drop half the time, and always while there are fewer than three
    if getrandbits(1) == 0 or len(drops) < 3:
        # never in or beside the column of the drop before
        x = last_drop
        while abs(x - last_drop) < 2:
            x = getrandbits(5) % COLUMNS
        last_drop = x
        drops.append([x, 0, 3 + getrandbits(2)])
    dots = bytearray(COLUMNS * ROWS)
    for drop in drops:
        x, y, length = drop
        for below in range(length):
            if 0 <= y - below < ROWS:
                dots[(y - below) * COLUMNS + x] = 1
        drop[1] += 1
    drops = [drop for drop in drops if drop[1] - drop[2] < ROWS]
    return dots


# each dot's angle round the middle in turns, and its distance from it in dots
ANGLES = [math.atan2(i // COLUMNS - MIDDLE, i % COLUMNS - MIDDLE) / (2 * math.pi) for i in range(COLUMNS * ROWS)]
DISTANCES = [math.sqrt((i % COLUMNS - MIDDLE) ** 2 + (i // COLUMNS - MIDDLE) ** 2) for i in range(COLUMNS * ROWS)]
SPIRAL_ARMS = 3


def spiral(step):
    return bytearray((ANGLES[i] * SPIRAL_ARMS + DISTANCES[i] * 0.12 - step * 0.03) % 1 < 0.42
                     for i in range(COLUMNS * ROWS))


# rows a grain falls each step, and the chances each step of the spout
# dropping a grain
FALL = 2
POURS = 6

sand = bytearray(COLUMNS * ROWS)
draining = False


# moves each grain a row, from the bottom up. it falls if it can, else it
# slides down a side. returns whether any grain rests near the top
def settle():
    resting_high = False
    for y in range(ROWS - 2, -1, -1):
        for x in range(COLUMNS):
            i = y * COLUMNS + x
            if not sand[i]:
                continue
            below = i + COLUMNS
            sides = (-1, 1) if getrandbits(1) else (1, -1)
            for target in [below] + [below + side for side in sides if 0 <= x + side < COLUMNS]:
                if not sand[target]:
                    sand[i], sand[target] = 0, 1
                    break
            else:
                resting_high = resting_high or y <= 3
    return resting_high


# grains poured in bursts from a spout drifting along the top. they fall and
# slide off each other into heaps. once a heap nears the top they drain
# through the floor
def falling_sand(step):
    global draining
    if step == 0:
        sand[:] = bytes(COLUMNS * ROWS)
        draining = False
    if draining:
        for i in range((ROWS - 1) * COLUMNS, ROWS * COLUMNS):
            sand[i] = 0
        draining = any(sand)
    resting_high = False
    for _ in range(FALL):
        resting_high = settle() or resting_high
    if not draining:
        draining = resting_high
        # bursts and lulls, the grains scattered about the spout
        spout = MIDDLE + (MIDDLE - 2) * math.sin(step * 0.05)
        pour = 0.05 + 0.7 * max(0, math.sin(step * 0.09)) ** 2
        for _ in range(POURS):
            if getrandbits(8) < pour * 256:
                sand[max(0, min(COLUMNS - 1, int(spout) + getrandbits(3) % 5 - 2))] = 1
    return sand


# the config page's name for each, in the order they take turns
PATTERNS = (
    ("waves", waves), ("spiral", spiral), ("rings", rings),
    ("life", game_of_life), ("sand", falling_sand), ("rain", rain),
)
NAMES = [name for name, _ in PATTERNS]

# unknown names fall back to cycle so the config page ticks what's showing
if pattern not in NAMES:
    pattern = "cycle"
cycling = pattern == "cycle"

# the pattern showing, when it started and its step. -1 so step 0 runs on the
# next update
showing = 0 if cycling else NAMES.index(pattern)
started = time.ticks_ms()
step = -1


def update():
    global step, showing, started
    now = time.ticks_ms()
    ran = time.ticks_diff(now, started)
    if cycling and ran >= SHOW:
        showing = (showing + 1) % len(PATTERNS)
        started = now
        ran = 0
        step = -1
    if ran // STEP != step:
        step = ran // STEP
        want(PATTERNS[showing][1](step), now)

    turn(now)
    screen.blit(board, 0, 0)
