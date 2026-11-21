# weather scenes: the scenery. the land from the horizon down, the tree that
# sways in the wind, and the grass, flowers, puddles and leaves in front of
# it. sky.py draws the sky behind all this, and the fog, rain and snow over it.
#
# the land is a beach, frost, snow, or the countryside in one of the four
# seasons: blossom and flowers in spring, full leaf in summer, turned leaves
# falling over stubble in autumn, and a bare tree over dull fields in winter.
# on the days festive.py dresses the scene up, the tree is a fir for christmas
# and bare for halloween, and DRESS draws that day's things onto the land
import math
import micropython
from array import array
from micropython import const

# the far horizon's screen y. the core copies it into w["horizon"] for sky.py
HORIZON = const(70)

# hills and the headland reach up to TOP, so those rows are blended over the
# sky. below the horizon the land covers everything and is copied straight in
TOP = const(52)

# a viper pixel's alpha byte, fully opaque
OPAQUE = const(-16777216)

# the trees work in 1/16 px, and angles in 1/16384 turn
TURN = const(16384)

# what viper looks things up in: the palette, square roots x16, then a sine
# wave of 256 steps x4096
SQRT = const(64)
SINE = const(328)
LUT = array("i", [0] * (SINE + 256))
for i in range(257):
    LUT[SQRT + i] = int(math.sqrt(i) * 16)
for i in range(256):
    LUT[SINE + i] = int(math.sin(i * math.pi / 128) * 4096)

# a small fixed generator, so the land and trees come out the same every boot
# without disturbing the random module other code relies on
_seed = [0x2545F491]


def rand(n):
    _seed[0] = (_seed[0] * 1103515245 + 12345) & 0x7fffffff
    return (_seed[0] >> 8) % n


def frand(low, high):
    return low + (high - low) * rand(10000) / 10000


# palette slots by name, filled in for the scene and the light
SLOTS = {}


def put(table, at, values):
    for i, value in enumerate(values):
        table[at + i] = value


def slot(name):
    if name not in SLOTS:
        SLOTS[name] = len(SLOTS)
    return SLOTS[name]


# ---- skeletons ------------------------------------------------------------------

# a tree is a list of bones. per node, where a bone ends: its parent (-1 for
# the base), length in 1/16 px, angle from its parent's, share of the trunk's
# bend x256, how far the wind turns it x256, flutter angle, flutter phase and
# flutter speed x16. a node with a length of -1 sits part way between two
# others instead: parent, -1, the other, how far along x256
NODE = const(8)


# the node names of the skeleton made last, for scene() to keep with its tree
_named = {}


def skeleton(bones):
    global _named
    names = _named = {}
    table = array("i", [0] * (NODE * len(bones) + 1))
    for i, bone in enumerate(bones):
        names[bone[0]] = i
        at = i * NODE
        if isinstance(bone[1], tuple):
            first, other, share = bone[1]
            put(table, at, (names[first], -1, names[other], int(share * 256)))
            continue
        parent, length, angle, bend, wind, flutter, speed = bone[1:]
        put(table, at, (names[parent] if parent else -1, int(length * 16), int(angle * TURN / 360), bend, wind,
                        int(flutter * TURN / 360), rand(TURN), speed))
    table[NODE * len(bones)] = -99
    return table, names


# per shape drawn: kind, two nodes, a radius at each end (a disc has one, a
# triangle's third node goes there), palette slot, offset across and down in
# 1/16 px, and the length between the nodes if that never changes, else 0
PRIM = const(9)
CAPSULE = const(0)
DISC = const(1)
TRIANGLE = const(2)


def shapes(names, items):
    table = array("i", [0] * (PRIM * len(items) + 1))
    for i, item in enumerate(items):
        kind = item[0]
        if kind == CAPSULE:
            _, first, second, start, end, colour, across, down, length = item
            row = [kind, names[first], names[second], int(start * 16), int(end * 16)]
        elif kind == DISC:
            _, first, radius, colour, across, down = item
            length = 0
            row = [kind, names[first], names[first], int(radius * 16), 0]
        else:
            _, first, second, third, colour, across, down = item
            length = 0
            row = [kind, names[first], names[second], names[third], 0]
        put(table, i * PRIM, row + [slot(colour), int(across * 16), int(down * 16), int(length * 16)])
    table[PRIM * len(items)] = -1
    return table


# where each node is this frame: x, y in 1/16 px and its angle
AT = array("i", [0] * 3 * 160)

# per frame: the base's x and y in 1/16 px, the trunk's bend, how far the
# wind turns the branches, flutter strength x256 and the flutter clock
MOTION = array("i", [0] * 6)


# lays out every node from the base up. each takes its parent's angle and adds
# its own, its share of the trunk's bend, a turn downwind and a flutter, then
# reaches out its length. the wind turns a bone most when it points upwind,
# so branches on the windward side swing over and those downwind trail
@micropython.viper
def pose(nodes: ptr32, at: ptr32, motion: ptr32, lut: ptr32):  # noqa: F821
    blow = motion[3]
    flutter = motion[4]
    clock = motion[5]
    n = 0
    out = 0
    while nodes[n] != -99:
        parent = nodes[n]
        length = nodes[n + 1]
        if length < 0:
            a = parent * 3
            b = nodes[n + 2] * 3
            share = nodes[n + 3]
            at[out] = at[a] + (((at[b] - at[a]) * share) >> 8)
            at[out + 1] = at[a + 1] + (((at[b + 1] - at[a + 1]) * share) >> 8)
            at[out + 2] = at[a + 2]
        else:
            x = motion[0]
            y = motion[1]
            angle = 0
            if parent >= 0:
                x = at[parent * 3]
                y = at[parent * 3 + 1]
                angle = at[parent * 3 + 2]
            angle += nodes[n + 2] + ((motion[2] * nodes[n + 3]) >> 8)
            if nodes[n + 4]:
                sine = lut[SINE + ((angle >> 6) & 255)]
                if blow < 0:
                    sine = 0 - sine
                angle += (((blow * nodes[n + 4]) >> 8) * (1434 + (((4096 - sine) * 1331) >> 12))) >> 12
            if nodes[n + 5]:
                phase = nodes[n + 6] + ((clock * nodes[n + 7]) >> 4)
                # and a quicker wobble on top, so it never settles into a rhythm
                wobble = lut[SINE + ((phase >> 6) & 255)] + (lut[SINE + ((phase >> 5) & 255)] >> 1)
                angle += (((nodes[n + 5] * flutter) >> 8) * wobble) >> 12
            j = (angle >> 6) & 255
            part = angle & 63
            sine = lut[SINE + j]
            sine += ((lut[SINE + ((j + 1) & 255)] - sine) * part) >> 6
            j = (j + 64) & 255
            cosine = lut[SINE + j]
            cosine += ((lut[SINE + ((j + 1) & 255)] - cosine) * part) >> 6
            at[out] = x + ((length * sine) >> 12)
            at[out + 1] = y - ((length * cosine) >> 12)
            at[out + 2] = angle
        n += NODE
        out += 3


# draws the shapes in order, antialiased across their edges: capsules are
# tapered strokes from node to node, discs sit on a node and triangles join
# three. each fills line by line. lines are rows, but a capsule that runs more
# across than down fills column by column so its long edges stay smooth
@micropython.viper
def paint(pixels: ptr32, prims: ptr32, at: ptr32, lut: ptr32):  # noqa: F821
    p = 0
    while prims[p] >= 0:
        kind = prims[p]
        colour = lut[prims[p + 5]]
        alpha = (colour >> 24) & 0xff
        alpha += alpha >> 7
        red_blue = colour & 0xff00ff
        green = colour & 0xff00
        across = prims[p + 6]
        down = prims[p + 7]
        node = prims[p + 1] * 3
        ax = at[node] + across
        ay = at[node + 1] + down
        node = prims[p + 2] * 3
        bx = at[node] + across
        by = at[node + 1] + down
        cx = 0
        cy = 0
        ra = prims[p + 3]
        rb = prims[p + 4]
        dx = 0
        dy = 1
        widen = 0
        step = 1
        if kind == 0:
            dx = bx - ax
            dy = by - ay
            if (dx if dx > 0 else 0 - dx) > (dy if dy > 0 else 0 - dy):
                ax, ay = ay, ax
                bx, by = by, bx
                dx, dy = dy, dx
                step = 128
            if dy < 0:
                ax, bx = bx, ax
                ay, by = by, ay
                ra, rb = rb, ra
                dx = 0 - dx
                dy = 0 - dy
            length = prims[p + 8]
            if length == 0:
                # the square root, a bit at a time
                left = dx * dx + dy * dy
                bit = 1 << 26
                while bit > left:
                    bit >>= 2
                while bit:
                    if left >= length + bit:
                        left -= length + bit
                        length = (length >> 1) + bit
                    else:
                        length >>= 1
                    bit >>= 2
            if dy == 0:
                dy = 1
            # a line cuts the stroke at a slant, so it's wider than the radius
            widen = (length << 8) // dy
            first = (ay + 7) >> 4
            last = ((by + 7) >> 4) - 1
        elif kind == 1:
            first = (ay - ra) >> 4
            last = (ay + ra - 1) >> 4
        else:
            node = ra * 3
            cx = at[node] + across
            cy = at[node + 1] + down
            # top to bottom: a, b, c
            if by < ay:
                ax, bx = bx, ax
                ay, by = by, ay
            if cy < by:
                bx, cx = cx, bx
                by, cy = cy, by
                if by < ay:
                    ax, bx = bx, ax
                    ay, by = by, ay
            first = (ay + 7) >> 4
            last = ((cy + 7) >> 4) - 1
        if first < 0:
            first = 0
        if last > 127:
            last = 127
        line = first
        while line <= last:
            middle = (line << 4) + 8
            weight = alpha
            left = 0
            right = 0
            if kind == 0:
                t = ((middle - ay) << 8) // dy
                centre = ax + ((dx * t) >> 8)
                half = ((ra + (((rb - ra) * t) >> 8)) * widen) >> 8
                left = centre - half
                right = centre + half
            elif kind == 1:
                away = middle - ay
                if away < 0:
                    away = 0 - away
                inside = ra * ra - away * away
                if inside > 0:
                    half = (ra * lut[SQRT + (inside << 8) // (ra * ra)]) >> 8
                    left = ax - half
                    right = ax + half
                if away > ra - 8:
                    weight = (alpha * (ra + 8 - away)) >> 4
            elif middle >= ay and middle < cy:
                left = ax + ((cx - ax) * (middle - ay)) // (cy - ay)
                if middle < by:
                    right = ax + ((bx - ax) * (middle - ay)) // (by - ay)
                else:
                    right = bx + ((cx - bx) * (middle - by)) // (cy - by)
                if right < left:
                    left, right = right, left
            if right > left:
                low = left >> 4
                high = (right - 1) >> 4
                x = low if low > 0 else 0
                end = high if high < 127 else 127
                here = (line << 7) + x if step == 1 else (x << 7) + line
                while x <= end:
                    cover = 16
                    if x == low:
                        cover = 16 - (left & 15)
                    if x == high:
                        cover += ((right - 1) & 15) - 15
                    cover = (cover * weight) >> 4
                    if cover >= 256:
                        pixels[here] = colour
                    elif cover > 0:
                        under = pixels[here]
                        pixels[here] = OPAQUE | ((((under & 0xff00ff) * (256 - cover) + red_blue * cover) >> 8) & 0xff00ff) | ((((under & 0xff00) * (256 - cover) + green * cover) >> 8) & 0xff00)
                    x += 1
                    here += step
            line += 1
        p += PRIM


# ---- the trees -------------------------------------------------------------------

# where each tree's trunk meets the ground, in px. right of centre, clear of
# the temperature in the bottom left
TREE_AT = (92, 115)
PALM_AT = (106, 123)


# a trunk, each bone taking more of the bend than the one below so it curves
# rather than tips over, with two roots splaying out at its foot
def trunk(lengths, angles, shares):
    bones = [("base", None, 0, 0, 0, 0, 0, 0)]
    for i in range(len(lengths)):
        bones.append(("t%d" % (i + 1), "t%d" % i if i else "base", lengths[i], angles[i], shares[i], 0, 0, 0))
    bones.append(("root_l", "base", 5, -100, 0, 0, 0, 0))
    bones.append(("root_r", "base", 5, 98, 0, 0, 0, 0))
    return bones


# the bark: strokes up the trunk, with a lit stripe down its left side
def bark(radii, dark, lit):
    items = [(CAPSULE, "base", "root_l", 1.8, 0.5, dark, 0, 0, 5), (CAPSULE, "base", "root_r", 1.8, 0.5, dark, 0, 0, 5)]
    for i in range(len(radii) - 1):
        start = "t%d" % i if i else "base"
        items.append((CAPSULE, start, "t%d" % (i + 1), radii[i], radii[i + 1], dark, 0, 0, 0))
        items.append((CAPSULE, start, "t%d" % (i + 1), radii[i] * 0.45, radii[i + 1] * 0.45, lit, -radii[i] * 0.4, 0, 0))
    return items


# a summer tree: limbs spreading from the trunk, a crown of leafy clumps on
# them. the outer limbs give more to the wind and flutter more
def leafy():
    bones = trunk((9, 9, 8, 7), (1, -3, 3, 2), (32, 48, 64, 80))
    # name, parent, length, angle, wind, flutter, flutter speed, clump radius
    limbs = (
        ("l1", "t2", 12, -52, 70, 1.5, 20, 0),
        ("l1b", "l1", 10, 18, 140, 2.5, 26, 8),
        ("l1c", "l1b", 7, 14, 190, 4, 31, 6),
        ("l2", "t3", 12, -26, 80, 1.5, 22, 7),
        ("l2b", "l2", 9, 10, 170, 3, 28, 9),
        ("c1", "t4", 11, -6, 80, 1.5, 21, 8),
        ("c1b", "c1", 9, 5, 170, 3, 30, 9),
        ("r2", "t4", 12, 30, 80, 1.5, 23, 7),
        ("r2b", "r2", 9, -8, 170, 3, 27, 9),
        ("r1", "t3", 12, 58, 70, 1.5, 19, 0),
        ("r1b", "r1", 9, -16, 140, 2.5, 25, 8),
        ("r1c", "r1b", 6, -12, 190, 4, 33, 6),
    )
    for name, parent, length, angle, wind, flutter, speed, _ in limbs:
        bones.append((name, parent, length, angle, 24, wind, flutter, speed))
    nodes, names = skeleton(bones)
    items = bark((3.6, 3.0, 2.6, 2.2, 1.8), "bark", "bark_lit")
    for name, parent, length, _, _, _, _, _ in limbs:
        thick = 1.5 if parent[0] == "t" else 1.0
        items.append((CAPSULE, parent, name, thick, thick * 0.7, "bark", 0, 0, length))
    clumps = [(name, radius) for name, _, _, _, _, _, _, radius in limbs if radius] + [("t4", 9)]
    # the crown's shadowed underside, then its body, then the light on the
    # clumps at the top and on the left
    for name, radius in clumps:
        items.append((DISC, name, radius, "leaf_dark", 1.2, 1.6))
    for name, radius in clumps:
        items.append((DISC, name, radius * 0.84, "leaf", -0.3, -0.4))
    for name in ("l1b", "l1c", "l2b", "c1b", "l2", "r2b"):
        radius = dict(clumps)[name]
        items.append((DISC, name, radius * 0.5, "leaf_lit", -radius * 0.3, -radius * 0.38))
    return nodes, shapes(names, items)


# a winter tree, bare. each limb forks twice into thinner twigs, iced on top
def bare():
    bones = trunk((9, 9, 8, 7), (1, -3, 3, 2), (32, 48, 64, 80))
    limbs = []

    def grow(parent, name, depth, angle, length):
        bones.append((name, parent, length, angle, 20 + depth * 4, 70 + 60 * depth, 1 + depth * 1.4, 18 + depth * 5))
        limbs.append((parent, name, depth, length))
        if depth < 2:
            spread = frand(18, 30)
            grow(name, name + "a", depth + 1, -spread + frand(-6, 6), length * frand(0.62, 0.74))
            grow(name, name + "b", depth + 1, spread * 0.8 + frand(-6, 6), length * frand(0.6, 0.72))

    for i, (parent, angle, length) in enumerate((("t4", -34, 13), ("t4", 4, 14), ("t4", 38, 13), ("t3", -64, 11), ("t3", 60, 11))):
        grow(parent, "m%d" % i, 0, angle, length)
    nodes, names = skeleton(bones)
    items = bark((3.6, 3.0, 2.6, 2.2, 1.8), "twig", "twig_lit")
    thickness = ((1.6, 1.1), (1.0, 0.7), (0.6, 0.4))
    for parent, name, depth, length in limbs:
        start, end = thickness[depth]
        items.append((CAPSULE, parent, name, start, end, "twig", 0, 0, length))
    for parent, name, depth, length in limbs:
        if depth < 2:
            start, end = thickness[depth]
            items.append((CAPSULE, parent, name, start * 0.5, end * 0.5, "rime", 0, -start * 0.6, length))
    return nodes, shapes(names, items)


# a fir under snow: tiers of boughs up a stiff trunk, snow lying on each
def fir():
    bones = [("base", None, 0, 0, 0, 0, 0, 0)]
    # each tier's height up the trunk, half its width and how far its top rises
    tiers = ((8, 21, 16), (18, 17, 15), (28, 13, 14), (37, 9, 12), (45, 5, 10))
    parent = "base"
    height = 0
    for i, (up, half, rise) in enumerate(tiers):
        name = "f%d" % i
        bones.append((name, parent, up - height, 0, 18 + i * 10, 0, 0, 0))
        height = up
        parent = name
        reach = half / 0.94
        bones.append(("top%d" % i, name, rise, 0, 0, 30, 0.6, 20))
        bones.append(("left%d" % i, name, reach, -110, 0, 50 + i * 10, 1.5, 24 + i))
        bones.append(("right%d" % i, name, reach, 110, 0, 50 + i * 10, 1.5, 26 + i))
        bones.append(("snow_l%d" % i, ("top%d" % i, "left%d" % i, 0.6)))
        bones.append(("snow_r%d" % i, ("top%d" % i, "right%d" % i, 0.6)))
        bones.append(("snow_m%d" % i, ("snow_l%d" % i, "snow_r%d" % i, 0.5)))
    nodes, names = skeleton(bones)
    items = [(CAPSULE, "base", "f0", 2.4, 2.0, "fir_bark", 0, 0, 8)]
    for i in range(len(tiers)):
        size = 1.3 + tiers[i][1] * 0.07
        items += [(TRIANGLE, "top%d" % i, "left%d" % i, "right%d" % i, "fir_dark", 0, 0),
                  (TRIANGLE, "top%d" % i, "left%d" % i, "f%d" % i, "fir", 0, 0),
                  (TRIANGLE, "top%d" % i, "snow_l%d" % i, "snow_r%d" % i, "snow", 0, 0),
                  (DISC, "snow_l%d" % i, size, "snow", 0.4, 0.4),
                  (DISC, "snow_m%d" % i, size * 1.1, "snow", 0, 0.6),
                  (DISC, "snow_r%d" % i, size, "snow_shade", -0.4, 0.4),
                  (DISC, "left%d" % i, size * 0.8, "snow", 0.5, -0.6),
                  (DISC, "right%d" % i, size * 0.8, "snow_shade", -0.5, -0.6)]
    # snow banked round the foot of the trunk
    items += [(DISC, "base", 5, "snow_shade", 1.2, 2.2), (DISC, "base", 4.4, "snow", -1.0, 1.8)]
    return nodes, shapes(names, items)


# a palm leaning out over the sand, fronds arching from its crown. the wind
# turns the fronds, more toward their tips, so they stream out downwind
def palm():
    angles = (-3, -4, -4, -4, -3, -3)
    bones = [("base", None, 0, 0, 0, 0, 0, 0)]
    for i, angle in enumerate(angles):
        name = "t%d" % (i + 1)
        bones.append((name, "t%d" % i if i else "base", 12, angle, 20 + i * 10, 0, 0, 0))
        # a ring round the trunk at each joint
        bones.append(("ring_l%d" % i, name, 2.5 - i * 0.12, -90, 0, 0, 0, 0))
        bones.append(("ring_r%d" % i, name, 2.5 - i * 0.12, 90, 0, 0, 0, 0))
    lean = sum(angles)
    fronds = (-140, -108, -76, -44, -12, 22, 54, 86, 118)
    for f, heading in enumerate(fronds):
        side = -1 if heading < 0 else 1
        previous = "t6"
        for k, (length, curl) in enumerate(((7, 0), (7, 18), (6, 22), (5, 26))):
            name = "f%d_%d" % (f, k)
            bones.append((name, previous, length, heading - lean if k == 0 else side * curl, 14, 110 + k * 50, 2 + k * 2.4, 22 + f % 3 * 3))
            if k:
                bones.append((name + "lo", name, 6 - k * 0.7, side * 110, 0, 80, 7, 40 + k * 4))
                bones.append((name + "hi", name, 4.5 - k * 0.5, side * 55, 0, 80, 7, 44 + k * 4))
            previous = name
    nodes, names = skeleton(bones)
    radii = (2.9, 2.7, 2.5, 2.3, 2.1, 1.9, 1.8)
    items = []
    for i in range(6):
        start = "t%d" % i if i else "base"
        items.append((CAPSULE, start, "t%d" % (i + 1), radii[i], radii[i + 1], "palm_bark", 0, 0, 12))
        items.append((CAPSULE, start, "t%d" % (i + 1), radii[i] * 0.4, radii[i + 1] * 0.4, "palm_lit", -radii[i] * 0.45, 0, 12))
    for i in range(6):
        items.append((CAPSULE, "ring_l%d" % i, "ring_r%d" % i, 0.5, 0.5, "palm_ring", 0, 0, 0))
    items += [(DISC, "t6", 2.0, "coconut", -1.6, 1.8), (DISC, "t6", 2.0, "coconut", 1.5, 2.1)]
    # the leaflets hanging under each frond, the frond's stem over them
    for f in range(len(fronds)):
        for k in range(1, 4):
            name = "f%d_%d" % (f, k)
            items.append((CAPSULE, name, name + "lo", 1.0, 0.45, "frond_dark", 0, 0, 0))
            items.append((CAPSULE, name, name + "hi", 0.9, 0.4, "frond", 0, 0, 0))
    for f in range(len(fronds)):
        previous = "t6"
        for k, width in enumerate((1.6, 1.4, 1.1, 0.8)):
            name = "f%d_%d" % (f, k)
            items.append((CAPSULE, previous, name, width, width * 0.75, "frond" if k else "frond_lit", 0, 0, (7, 7, 6, 5)[k]))
            previous = name
    items.append((DISC, "t6", 1.8, "coconut", 0, 2.8))
    return nodes, shapes(names, items)


# ---- colour and light ------------------------------------------------------------

# the light the palette and the land were last drawn for: daylight, sunset
# glow, how much the cloud dulls things and whether it's raining
_day = 1.0
_dusk = 0.0
_dull = 0.0
_wet = False


# a colour as it looks in this light. lit is how much it faces the sun: lit
# surfaces warm most at sunset. at night everything goes dark, grey and a
# little blue, but keeps enough of itself to read
def tint(rgb, lit=1.0):
    r, g, b = rgb
    if _wet:
        r, g, b = r * 0.78, g * 0.8, b * 0.88
    if _dull:
        grey = 0.3 * r + 0.59 * g + 0.11 * b
        keep = 1 - 0.38 * _dull
        dim = 1 - 0.2 * _dull
        r, g, b = (grey + (r - grey) * keep) * dim, (grey + (g - grey) * keep) * dim, (grey + (b - grey) * keep) * dim
    if _dusk:
        warm = _dusk * (0.35 + 0.65 * lit) * (1 - 0.6 * _dull)
        r, g, b = r + (255 - r) * warm * 0.32, g * (1 - 0.06 * _dusk) + 18 * warm, b * (1 - 0.32 * warm)
    if _day < 1:
        grey = 0.3 * r + 0.59 * g + 0.11 * b
        dark = (grey * 0.17 + r * 0.08 + 6, grey * 0.22 + g * 0.08 + 10, grey * 0.3 + b * 0.08 + 22)
        r, g, b = dark[0] + (r - dark[0]) * _day, dark[1] + (g - dark[1]) * _day, dark[2] + (b - dark[2]) * _day
    return (min(255, max(0, int(r))), min(255, max(0, int(g))), min(255, max(0, int(b))))


def mix(first, second, amount):
    return (int(first[0] + (second[0] - first[0]) * amount), int(first[1] + (second[1] - first[1]) * amount),
            int(first[2] + (second[2] - first[2]) * amount))


# a colour as a viper pixel, 0xAABBGGRR, signed to fit an array("i")
def pack(rgb, alpha=255):
    value = (alpha << 24) | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0]
    return value - (1 << 32) if value >= (1 << 31) else value


def pen(rgb, alpha=255):
    return color.rgb(rgb[0], rgb[1], rgb[2], alpha)


# name: day colour and how much it faces the sun
COLOURS = {
    "bark": ((78, 56, 40), 0.5), "bark_lit": ((136, 100, 66), 1),
    "leaf_dark": ((26, 80, 42), 0.4), "leaf": ((62, 138, 50), 0.8), "leaf_lit": ((112, 178, 64), 1),
    "twig": ((60, 50, 50), 0.5), "twig_lit": ((110, 96, 90), 1), "rime": ((214, 230, 246), 1),
    "fir_bark": ((70, 50, 40), 0.4), "fir_dark": ((18, 62, 50), 0.4), "fir": ((38, 104, 66), 0.9),
    "snow": ((240, 245, 255), 1), "snow_shade": ((180, 198, 232), 0.5),
    "palm_bark": ((146, 112, 76), 0.6), "palm_lit": ((200, 164, 112), 1), "palm_ring": ((92, 68, 46), 0.4),
    "frond_dark": ((30, 104, 50), 0.5), "frond": ((74, 160, 62), 0.8), "frond_lit": ((150, 206, 86), 1),
    "coconut": ((104, 74, 42), 0.5), "foam": ((244, 250, 252), 1), "ripple": ((200, 214, 230), 1),
    "poppy": ((230, 50, 40), 0.8), "daisy": ((246, 246, 238), 0.8), "buttercup": ((248, 208, 46), 0.8),
    "violet": ((170, 98, 220), 0.8),
}
# what each season does to those: the tree in blossom, then turned, and no ice
# on bare twigs unless there's a frost
SEASON_COLOURS = {
    "spring": {"leaf_dark": ((176, 104, 136), 0.4), "leaf": ((240, 168, 196), 0.8), "leaf_lit": ((255, 226, 236), 1)},
    "autumn": {"leaf_dark": ((126, 52, 26), 0.4), "leaf": ((208, 104, 30), 0.8), "leaf_lit": ((244, 176, 52), 1)},
    "winter": {"rime": ((122, 106, 98), 1)},
}
# and a theme: a christmas tree is green unless there's frost or snow to lie on
# it, and a halloween one is dark, with no ice unless there's a frost
THEME_COLOURS = {
    "christmas": {"snow": ((60, 132, 80), 1), "snow_shade": ((26, 84, 58), 0.5)},
    "halloween": {"twig": ((36, 30, 38), 0.5), "twig_lit": ((74, 62, 72), 1), "rime": ((74, 62, 72), 1)},
}
WHITE_LANDS = ("frost", "snow")
# blades of grass, root to tip, per land, in two sets
GRASS = {
    "spring": (((40, 112, 36), (64, 146, 44), (100, 178, 56), (146, 210, 80)),
               ((34, 98, 42), (54, 128, 48), (84, 160, 58), (122, 192, 74))),
    "summer": (((34, 100, 34), (54, 132, 40), (84, 162, 50), (124, 196, 70)),
               ((28, 86, 40), (44, 114, 44), (68, 144, 52), (100, 176, 64))),
    "autumn": (((70, 86, 34), (106, 116, 42), (150, 146, 52), (196, 176, 76)),
               ((62, 74, 36), (92, 100, 42), (130, 126, 50), (172, 154, 68))),
    "winter": (((58, 78, 44), (82, 100, 52), (110, 124, 64), (144, 150, 86)),
               ((50, 68, 44), (72, 88, 50), (98, 110, 60), (128, 136, 80))),
    "frost": (((84, 110, 116), (124, 152, 162), (172, 194, 208), (222, 234, 246)),
              ((70, 96, 104), (110, 138, 150), (156, 182, 198), (206, 222, 240))),
    "snow": (((96, 84, 64), (124, 110, 82), (152, 138, 104), (180, 168, 136)),
             ((84, 74, 58), (110, 98, 74), (138, 126, 96), (166, 154, 124))),
    "beach": (((118, 124, 66), (148, 156, 84), (182, 184, 110), (214, 210, 150)),
              ((104, 112, 60), (132, 142, 76), (166, 170, 100), (198, 196, 136))),
}
# leaves blown across in a strong wind. in spring they're petals
BLOWN = {
    "spring": ((255, 214, 228), (244, 170, 198), (255, 240, 244)),
    "summer": ((96, 156, 52), (150, 176, 60), (196, 160, 52)),
    "autumn": ((214, 104, 30), (176, 60, 28), (240, 176, 50)),
    "winter": ((140, 96, 54), (112, 76, 46), (160, 124, 70)),
    "frost": ((176, 112, 50), (140, 80, 42), (196, 152, 70)),
}
# the wind petals and leaves come out in, km/h, and the fewest then. spring's
# petals drift on a breeze and autumn's leaves fall in still air
LOOSE = {"spring": (6, 3), "autumn": (0, 4)}

for name in list(COLOURS) + ["grass%d" % i for i in range(8)] + ["blown%d" % i for i in range(3)]:
    slot(name)


def palette(kind, theme):
    season = SEASON_COLOURS.get(kind, {})
    themed = {} if kind in WHITE_LANDS else THEME_COLOURS.get(theme, {})
    for name in COLOURS:
        rgb, lit = themed.get(name) or season.get(name, COLOURS[name])
        LUT[SLOTS[name]] = pack(tint(rgb, lit))
    for i in range(8):
        LUT[SLOTS["grass%d" % i]] = pack(tint(GRASS[kind][i // 4][i % 4], 0.4 + 0.2 * (i % 4)))
    for i in range(3):
        LUT[SLOTS["blown%d" % i]] = pack(tint(BLOWN.get(kind, BLOWN["summer"])[i], 0.8))


# ---- the land ----------------------------------------------------------------------

# drawn into LAND once for each scene and light, then copied to the screen
# every frame. rows above the horizon are blended, as hills stand against the sky
LAND = image(128, 128)
LAND_PIXELS = memoryview(LAND)
BAND = LAND.window(0, TOP, 128, HORIZON - TOP)
HEADLAND_BAND = LAND.window(0, TOP, 48, HORIZON - TOP)
BAND_AT = vec2(0, TOP)
CLEAR = bytes(HORIZON * 512)


# points along a natural looking ridge, overlapping slow waves at random
# phases. lumps(x), 0 to 1, shapes it along its length
def ridge(left, right, base, height, step=4, lumps=None):
    phases = [frand(0, 6.283) for _ in range(3)]
    points = []
    x = left
    while True:
        wave = 0.5 * math.sin(x * 0.045 + phases[0]) + 0.3 * math.sin(x * 0.11 + phases[1]) + 0.2 * math.sin(x * 0.27 + phases[2])
        points.append((x, base - height * (lumps(x) if lumps else 1) * (0.55 + 0.45 * wave)))
        if x >= right:
            return points
        x = min(right, x + step)


# the ridge's height at x
def height_at(points, x):
    for i in range(1, len(points)):
        if points[i][0] >= x:
            (x0, y0), (x1, y1) = points[i - 1], points[i]
            return y0 + (y1 - y0) * (x - x0) / max(1, x1 - x0)
    return points[-1][1]


def solid(points, bottom=128):
    return shape.custom([vec2(x, y) for x, y in points] + [vec2(points[-1][0], bottom), vec2(points[0][0], bottom)])


def ellipse(x, y, across, down):
    return shape.custom([vec2(x + across * math.cos(i * 0.314), y + down * math.sin(i * 0.314)) for i in range(20)])


def gradient(top, bottom, y0, y1, alpha=255):
    return brush.gradient(brush.LINEAR, 0, y0, 0, y1, ((0.0, pen(top, alpha)), (1.0, pen(bottom, alpha))))


# the sky's colour along a row of the screen, as sky.py drew it this frame
def sample(y):
    pixels = memoryview(screen)
    totals = [0, 0, 0]
    for x in range(4, 128, 16):
        at = (y * 128 + x) * 4
        for channel in range(3):
            totals[channel] += pixels[at + channel]
    return (totals[0] // 8, totals[1] // 8, totals[2] // 8)


# puddles when it rains, x, y, half width and height, then the sea for rain
# rings on the beach
WATERS = ((34, 105, 13, 3), (60, 120, 10, 2.6), (121, 122, 6, 1.8), (64, 81, 90, 10))

COUNTRY = {
    # far hills top and foot, nearer hills top and foot, their fields, hedges, then the meadow top and foot
    # fresh green, and a field of rape in flower
    "spring": ((128, 176, 150), (104, 156, 128), (112, 176, 72), (90, 150, 60),
               ((136, 196, 76), (104, 170, 64), (228, 214, 66), (150, 198, 98), (120, 184, 88)),
               (60, 118, 52), (126, 200, 70), (60, 138, 46)),
    "summer": ((120, 166, 140), (96, 146, 118), (94, 156, 62), (76, 134, 54),
               ((118, 178, 64), (92, 152, 56), (160, 180, 72), (200, 186, 92), (106, 164, 78)),
               (52, 102, 46), (110, 186, 60), (50, 122, 40)),
    # stubble and ploughed earth between hedges gone brown
    "autumn": ((150, 150, 126), (126, 130, 106), (152, 146, 70), (124, 116, 56),
               ((200, 164, 72), (146, 100, 58), (178, 152, 62), (124, 130, 58), (210, 180, 98)),
               (110, 76, 40), (152, 160, 62), (92, 104, 40)),
    # tired grass and bare earth
    "winter": ((134, 150, 150), (114, 130, 130), (114, 128, 86), (94, 106, 72),
               ((126, 138, 90), (112, 98, 74), (140, 142, 100), (100, 116, 78), (130, 124, 92)),
               (66, 60, 52), (120, 136, 80), (72, 90, 54)),
    "frost": ((168, 186, 206), (150, 170, 192), (170, 190, 200), (150, 172, 184),
              ((182, 200, 206), (162, 182, 192), (194, 206, 212), (156, 176, 186), (176, 194, 202)),
              (96, 112, 120), (204, 220, 230), (150, 176, 192)),
    "snow": ((208, 218, 238), (188, 202, 228), (234, 240, 252), (212, 222, 244),
             ((238, 242, 252), (222, 230, 248), (244, 247, 254), (214, 224, 244), (232, 238, 252)),
             (112, 120, 134), (248, 250, 255), (204, 216, 240)),
}

# shapes for the countryside and the coast, made the first time they're needed
_made = {}


# the countryside's shapes: far hills, nearer hills of fields split by hedges
# and dotted with copses, and the meadow the tree stands in
def countryside():
    far = ridge(-2, 130, 66, 12)
    middle = ridge(-2, 130, 77, 10)
    near = ridge(-2, 130, 93, 10, 4, lambda x: 0.55 + 0.6 * x / 128)
    bottom = 98

    # the fields' sides fan out toward us
    def side(x, y):
        top = height_at(middle, x)
        return x + (x - 64) * 0.6 * (y - top) / (bottom - top)

    fields = []
    hedges = []
    edges = (-2, 13, 31, 52, 71, 90, 109, 130)
    for i in range(len(edges) - 1):
        left, right = edges[i], edges[i + 1]
        hedge_left = height_at(middle, left) + 6 + rand(3)
        hedge_right = height_at(middle, right) + 6 + rand(3)
        upper = ([vec2(left, height_at(middle, left))] + [vec2(x, y) for x, y in middle if left < x < right] +
                 [vec2(right, height_at(middle, right)), vec2(side(right, hedge_right), hedge_right), vec2(side(left, hedge_left), hedge_left)])
        lower = [vec2(side(left, hedge_left), hedge_left), vec2(side(right, hedge_right), hedge_right),
                 vec2(side(right, bottom), bottom), vec2(side(left, bottom), bottom)]
        fields += [(shape.custom(upper), (i * 2) % 5), (shape.custom(lower), (i * 3 + 1) % 5)]
        hedges.append(shape.line(side(left, hedge_left), hedge_left, side(right, hedge_right), hedge_right, 1.3))
        if i:
            hedges.append(shape.line(left, height_at(middle, left) + 0.5, side(left, bottom), bottom, 0.9))
    copses = []
    for x in (10, 38, 57, 84, 116):
        y = height_at(middle, x) + 5 + rand(4)
        copses.append([(x + frand(-2.5, 2.5), y + frand(-1, 0.6), frand(1.8, 2.8)) for _ in range(2 + rand(2))])
    return (solid(far), solid(middle), solid(near), near, fields, hedges, copses,
            ellipse(TREE_AT[0] + 2, TREE_AT[1] + 1, 17, 3.2), [ellipse(*water) for water in WATERS[:3]])


def country(kind, haze, high):
    if "country" not in _made:
        _made["country"] = countryside()
    far, middle, near, near_line, fields, hedges, copses, shadow, puddles = _made["country"]
    far_top, far_foot, mid_top, mid_foot, colours, hedge, near_top, near_foot = COUNTRY[kind]
    # farther hills fade into the sky at the horizon
    LAND.pen = gradient(mix(tint(far_top, 1), haze, 0.5), mix(tint(far_foot, 0.6), haze, 0.4), 54, 70)
    LAND.shape(far)
    LAND.pen = gradient(mix(tint(mid_top, 1), haze, 0.18), tint(mid_foot, 0.6), 64, 98)
    LAND.shape(middle)
    for field, colour in fields:
        LAND.pen = pen(mix(tint(colours[colour], 0.9), haze, 0.12))
        LAND.shape(field)
    LAND.pen = pen(mix(tint(hedge, 0.3), haze, 0.1))
    for line in hedges:
        LAND.shape(line)
    # copses, each a few trees bunched together, lit on top
    dark = mix(tint(hedge, 0.3), haze, 0.1)
    lit = mix(tint(mix(hedge, (255, 255, 255) if kind == "snow" else colours[0], 0.5), 1), haze, 0.1)
    for copse in copses:
        LAND.pen = pen(dark)
        for x, y, size in copse:
            LAND.circle(x, y, size)
        LAND.pen = pen(lit)
        for x, y, size in copse:
            LAND.circle(x - size * 0.3, y - size * 0.4, size * 0.55)
    LAND.pen = gradient(tint(near_top, 1), tint(near_foot, 0.5), 82, 128)
    LAND.shape(near)
    # the meadow's top edge catches the light
    LAND.pen = pen(tint(mix(near_top, (255, 255, 230), 0.2), 1), 120)
    for i in range(len(near_line) - 1):
        (x0, y0), (x1, y1) = near_line[i], near_line[i + 1]
        LAND.shape(shape.line(x0, y0 + 0.6, x1, y1 + 0.6, 1.2))
    if _wet and kind != "snow":
        for puddle, (x, y, across, down) in zip(puddles, WATERS):
            LAND.pen = pen(tint(mix(near_foot, (0, 0, 0), 0.4), 0.3))
            LAND.shape(ellipse(x, y + 0.6, across + 0.8, down + 0.6))
            LAND.pen = gradient(mix(high, tint(near_foot, 0.3), 0.3), mix(haze, tint(near_foot, 0.3), 0.45), y - down, y + down)
            LAND.shape(puddle)
    sun = _day * (1 - _dull)
    if sun > 0.1:
        LAND.pen = pen((0, 20, 0), int(70 * sun))
        LAND.shape(shadow)


# the edge of the sand down the beach, per column, in 1/16 px
SHORE = [int((95 + 2.5 * math.sin(x * 0.035 + 0.8) + math.sin(x * 0.11 + 2)) * 16) for x in range(128)]
LIGHTHOUSE_X = 10


# the coast's shapes: a headland across the bay with a lighthouse on it, the
# sand, a wet band along the water's edge and a dune
def coastline():
    def falls(x):
        along = min(1.0, max(0.0, x / 46))
        return 1 - along * along * (3 - 2 * along) + 0.08

    headland = ridge(-2, 48, HORIZON + 0.5, 15, 2, falls)
    edge = [vec2(x, SHORE[x] / 16) for x in range(0, 128, 4)] + [vec2(128, SHORE[127] / 16)]
    return (solid(headland, HORIZON + 1),
            shape.custom([vec2(x, y) for x, y in headland] + [vec2(x, y + 2.5 - x * 0.04) for x, y in reversed(headland)]),
            int(height_at(headland, LIGHTHOUSE_X)) + 1,
            shape.custom(edge + [vec2(128, 128), vec2(0, 128)]),
            shape.custom(edge + [vec2(p.x, p.y + 4) for p in reversed(edge)]),
            solid(ridge(-4, 58, 118, 7, 4, lambda x: max(0.0, 1 - (x / 58) ** 2))),
            ellipse(PALM_AT[0] - 10, PALM_AT[1] + 1, 15, 2.6))


def coast(haze, high):
    if "coast" not in _made:
        _made["coast"] = coastline()
    headland, grass, lighthouse, sand, wet, dune, shadow = _made["coast"]
    sea_top = mix(tint((150, 192, 214), 1), haze, 0.55)
    LAND.pen = brush.gradient(brush.LINEAR, 0, HORIZON, 0, 100, ((0.0, pen(sea_top)), (0.3, pen(tint((40, 118, 168), 0.7))),
                                                                  (1.0, pen(tint((40, 164, 176), 0.8)))))
    LAND.rectangle(0, HORIZON, 128, 32)
    # a bright line where the sea meets the sky
    LAND.pen = pen(mix(sea_top, high if _day > 0.5 else haze, 0.3), 160)
    LAND.rectangle(0, HORIZON, 128, 1)
    LAND.pen = gradient(mix(tint((150, 128, 104), 0.8), haze, 0.35), mix(tint((106, 92, 80), 0.4), haze, 0.25), 56, HORIZON)
    LAND.shape(headland)
    LAND.pen = pen(mix(tint((92, 140, 66), 1), haze, 0.35))
    LAND.shape(grass)
    LAND.pen = pen(mix(tint((238, 236, 230), 1), haze, 0.2))
    LAND.rectangle(LIGHTHOUSE_X - 1, lighthouse - 7, 3, 7)
    LAND.pen = pen(mix(tint((196, 60, 50), 0.8), haze, 0.2))
    LAND.rectangle(LIGHTHOUSE_X - 1, lighthouse - 9, 3, 2)
    LAND.rectangle(LIGHTHOUSE_X - 1, lighthouse - 4, 3, 1)
    LAND.pen = gradient(tint((240, 216, 162), 1), tint((216, 186, 128), 0.6), 90, 128)
    LAND.shape(sand)
    LAND.pen = brush.gradient(brush.LINEAR, 0, 92, 0, 101, ((0.0, pen(tint((176, 150, 110), 0.6), 230)), (1.0, pen(tint((200, 174, 128), 0.6), 0))))
    LAND.shape(wet)
    LAND.pen = gradient(tint((244, 222, 170), 1), tint((222, 194, 138), 0.6), 110, 128)
    LAND.shape(dune)
    sun = _day * (1 - _dull)
    if sun > 0.1:
        LAND.pen = pen((60, 30, 0), int(60 * sun))
        LAND.shape(shadow)
    return lighthouse


# ---- the sea ------------------------------------------------------------------------

# per frame: the clock in ms, then three waves rolling in, each its row in
# 1/16 px and its strength x256. then the surf's reach up the sand in 1/16 px,
# the surf's water and foam colours, and from 16 the edge of the sand per column
SEA = array("i", [0] * 16 + SHORE)
GLINT = const(6)


# glints on the water: per glint its row, x in 1/16 px, longest length in px,
# drift in 1/16 px a second, phase and how fast it comes and goes. nearer
# glints are longer and drift faster
def glints():
    items = []
    for row in range(HORIZON + 1, 95):
        near = (row - HORIZON) / 25
        for _ in range(3 + int(near * 3)):
            items += [row, rand(2048), 1 + int(near * 4 * frand(0.6, 1.3)), int((3 + near * 22) * frand(0.6, 1.4)) * (1 if rand(2) else -1),
                      rand(TURN), 6 + rand(10)]
    return array("i", items + [-1])


# each glint catches the brightest of a few bits of sky above it, different
# bits each time it shows, so the sun or moon breaks up into a glittering path
# under it and the rest of the sky into soft highlights. then the waves
# rolling in, and the surf running up the sand and back
@micropython.viper
def sea(pixels: ptr32, glints: ptr32, params: ptr32, lut: ptr32):  # noqa: F821
    clock = params[0]
    i = 0
    g = 0
    while glints[g] >= 0:
        row = glints[g]
        phase = glints[g + 4] + ((clock * glints[g + 5]) >> 6)
        sine = lut[SINE + ((phase >> 6) & 255)]
        if sine > 1400:
            x = ((glints[g + 1] + ((glints[g + 3] * clock) >> 10)) >> 4) & 127
            hashed = (phase >> 14) * 40503 + i * 9973
            best = 0
            bright = 0
            tries = 0
            while tries < 4:
                y = 2 * HORIZON - 1 - row - (((hashed >> (tries * 5)) & 31) << 1)
                if y < 2:
                    y = 2
                sky = pixels[(y << 7) | x]
                level = (sky & 0xff) + ((sky >> 8) & 0xff) + ((sky >> 16) & 0xff)
                if level > bright:
                    bright = level
                    best = sky
                tries += 1
            line = row << 7
            under = pixels[line | x]
            if bright > (under & 0xff) + ((under >> 8) & 0xff) + ((under >> 16) & 0xff) + 24:
                length = 1 + (((sine - 1400) * glints[g + 2]) >> 12)
                while length > 0:
                    length -= 1
                    here = line | ((x + length) & 127)
                    if bright > 540:
                        pixels[here] = best | OPAQUE
                    else:
                        under = pixels[here]
                        pixels[here] = OPAQUE | (((under & 0xfefefe) >> 1) + ((best & 0xfefefe) >> 1))
        i += 1
        g += GLINT

    foam = params[10]
    foam_red_blue = foam & 0xff00ff
    foam_green = foam & 0xff00
    wave = 0
    while wave < 3:
        strength = params[3 + wave * 2]
        row = params[2 + wave * 2] >> 4
        line = row << 7
        offset = wave * 83 + row * 3
        x = 0
        while strength > 0 and x < 128:
            # broken along its length, in pieces of all sizes
            if lut[SINE + ((x * 5 + offset) & 255)] + lut[SINE + ((x * 13 + offset * 3) & 255)] > 1500:
                here = line | x
                under = pixels[here]
                pixels[here] = OPAQUE | ((((under & 0xff00ff) * (256 - strength) + foam_red_blue * strength) >> 8) & 0xff00ff) | ((((under & 0xff00) * (256 - strength) + foam_green * strength) >> 8) & 0xff00)
            x += 1
        wave += 1

    reach = params[8]
    water = params[9] & 0xfefefe
    foam = foam & 0xfefefe
    x = 0
    while x < 128:
        edge = params[16 + x]
        ripple = (lut[SINE + ((x * 6 + (clock >> 5)) & 255)] * 3 + lut[SINE + ((x * 15 - (clock >> 4)) & 255)] * 2) >> 10
        front = (edge + reach + ripple) >> 4
        edge >>= 4
        # the waves break along the water's edge
        if ((x * 3 + (clock >> 7)) & 7) > 1:
            here = ((edge - 1) << 7) | x
            pixels[here] = OPAQUE | (((pixels[here] & 0xfefefe) >> 1) + (foam >> 1))
        y = edge
        while y < front and y < 128:
            here = (y << 7) | x
            pixels[here] = OPAQUE | (((pixels[here] & 0xfefefe) >> 1) + (water >> 1))
            y += 1
        if front >= edge and front < 128 and ((x * 5 + (clock >> 8)) & 7):
            here = (front << 7) | x
            pixels[here] = OPAQUE | (((pixels[here] & 0xfcfcfc) >> 2) + (((foam & 0xfcfcfc) >> 2) * 3))
        x += 1


# ---- grass, flowers and the rest -----------------------------------------------------

# per blade: x in 1/16 px, root row, height, the palette slot of the first of
# its four shades root to tip, flutter phase, and a flower's slot or 0
BLADE = const(6)

# per frame: how many blades, where the wind's history has got to, how far
# back in it each px across looks x256, 1 if the wind blows from the right,
# flutter x256, the flutter clock and how the flutter ripples across. then
# from 8 the wind over the last few seconds, km/h x16
WIND = array("i", [0] * (8 + 64))


@micropython.viper
def grass(pixels: ptr32, blades: ptr32, wind: ptr32, lut: ptr32):  # noqa: F821
    head = wind[1]
    delay = wind[2]
    flutter = wind[4]
    clock = wind[5]
    ripple = wind[6]
    b = 0
    finish = wind[0] * BLADE
    while b < finish:
        x16 = blades[b]
        root = blades[b + 1]
        height = blades[b + 2]
        column = x16 >> 4
        # gusts reach the blades on the upwind side first
        far = 127 - column if wind[3] else column
        lean = (wind[8 + ((head - ((far * delay) >> 8)) & 63)] * 38) >> 8
        if lean > 200:
            lean = 200
        elif lean < -200:
            lean = -200
        lean += (flutter * lut[SINE + ((blades[b + 4] + clock + column * ripple) & 255)]) >> 12
        tip = (lean * height) >> 4
        curve = (tip << 8) // (height * height)
        tone = 1024 // height
        shade = blades[b + 3]
        rows = height - ((tip if tip > 0 else 0 - tip) >> 6)
        k = 0
        x = x16
        y = root
        while k < rows:
            y = root - k
            x = x16 + ((curve * k * k) >> 8)
            column = x >> 4
            if 0 <= y < 128 and 0 <= column < 127:
                colour = lut[shade + ((k * tone) >> 8)]
                here = (y << 7) | column
                part = x & 15
                if part < 5:
                    pixels[here] = colour
                elif part > 10:
                    pixels[here + 1] = colour
                else:
                    colour = (colour & 0xfefefe) >> 1
                    pixels[here] = OPAQUE | (((pixels[here] & 0xfefefe) >> 1) + colour)
                    pixels[here + 1] = OPAQUE | (((pixels[here + 1] & 0xfefefe) >> 1) + colour)
            k += 1
        if blades[b + 5]:
            colour = lut[blades[b + 5]]
            column = (x + 8) >> 4
            if 1 <= y < 128 and 0 <= column < 127:
                here = ((y - 1) << 7) | column
                pixels[here] = colour
                pixels[here + 1] = colour
                pixels[here + 128] = colour
                pixels[here + 129] = colour
        b += BLADE


# rain rings spreading on puddles or the sea, each kept inside its water.
# first the count, colour, how long a ring lasts in ms and the time now. then
# per ring x and y in px, when it started and which water. the waters, from
# 64, are x, y, half width and half height each
RING = const(4)
RINGS = array("i", [0] * 64 + [int(value) for water in WATERS for value in water])


@micropython.viper
def rings(pixels: ptr32, items: ptr32, lut: ptr32):  # noqa: F821
    colour = items[1]
    red_blue = colour & 0xff00ff
    green = colour & 0xff00
    life = items[2]
    r = 4
    while r < 4 + items[0] * RING:
        age = items[3] - items[r + 2]
        if 0 <= age < life:
            water = 64 + items[r + 3] * 4
            across = items[water + 2]
            down = items[water + 3]
            bound = across * across * down * down
            # grows to 4 px across, fading as it goes
            radius = 16 + (age * 56) // life
            strength = 200 - (age * 200) // life
            point = 0
            while point < 256:
                x = items[r] + ((radius * lut[SINE + ((point + 64) & 255)]) >> 16)
                y = items[r + 1] + ((radius * lut[SINE + point]) >> 17)
                off_x = x - items[water]
                off_y = y - items[water + 1]
                if 0 <= x < 128 and 0 <= y < 128 and off_x * off_x * down * down + off_y * off_y * across * across <= bound:
                    here = (y << 7) | x
                    under = pixels[here]
                    pixels[here] = OPAQUE | ((((under & 0xff00ff) * (256 - strength) + red_blue * strength) >> 8) & 0xff00ff) | ((((under & 0xff00) * (256 - strength) + green * strength) >> 8) & 0xff00)
                point += 16
        r += RING


# glints of frost or snow catching the light: first the clock in ms and the
# colour, then x, y, phase and speed each
SPARKLE = const(4)


@micropython.viper
def sparkle(pixels: ptr32, items: ptr32, lut: ptr32):  # noqa: F821
    colour = items[1]
    red_blue = colour & 0xff00ff
    green = colour & 0xff00
    s = 2
    while items[s] >= 0:
        sine = lut[SINE + ((items[s + 2] + ((items[0] * items[s + 3]) >> 10)) & 255)]
        if sine > 3000:
            strength = ((sine - 3000) * 256) // 1096
            spot = 0
            while spot < 5:
                x = items[s]
                y = items[s + 1]
                if spot == 1:
                    x -= 1
                elif spot == 2:
                    x += 1
                elif spot == 3:
                    y -= 1
                elif spot == 4:
                    y += 1
                weight = strength if spot == 0 else ((strength - 128) * 2) // 3
                if weight > 0 and 0 <= x < 128 and 0 <= y < 128:
                    here = (y << 7) | x
                    under = pixels[here]
                    pixels[here] = OPAQUE | ((((under & 0xff00ff) * (256 - weight) + red_blue * weight) >> 8) & 0xff00ff) | ((((under & 0xff00) * (256 - weight) + green * weight) >> 8) & 0xff00)
                spot += 1
        s += SPARKLE


# leaves blown across: first the frame's ms, the wind in 1/16 px a second, how
# many leaves are out and a seed for where new ones start. then per leaf x
# and y in 1/16 px, tumble phase, how fast it tumbles and its palette slot
LEAF = const(5)
LEAVES = array("i", [0] * (4 + LEAF * 10))


@micropython.viper
def blow(pixels: ptr32, items: ptr32, lut: ptr32):  # noqa: F821
    step = items[0]
    speed = items[1]
    seed = items[3]
    s = 4
    while s < 4 + items[2] * LEAF:
        x = items[s]
        y = items[s + 1]
        phase = items[s + 2] + ((step * items[s + 3]) >> 6)
        sine = lut[SINE + (phase & 255)]
        # each leaf rides the wind at its own pace, bobbing as it tumbles
        x += (speed * step * (12 + (s & 3))) // 16000
        y += (sine * step) // 12800 + (step >> 3)
        if x < -128 or x > 2176 or y > 2048 or y < 640:
            seed = seed * 1664525 + 1013904223
            x = -96 if speed > 0 else 2144
            y = 960 + ((seed >> 8) & 1023)
        items[s] = x
        items[s + 1] = y
        items[s + 2] = phase
        x >>= 4
        y >>= 4
        colour = lut[items[s + 4]]
        if 0 <= y < 127 and 0 <= x < 127:
            here = (y << 7) | x
            pixels[here] = colour
            if sine > 1500:
                pixels[here + 1] = colour
            elif sine < -1500:
                pixels[here + 128] = colour
            else:
                pixels[here + 129] = colour
        s += LEAF
    items[3] = seed


# the blades, flowers and tufts for each land
def meadow(kind):
    blades = []
    first = SLOTS["grass0"]
    second = SLOTS["grass4"]

    def blade(x, root, height, shade, flower=0):
        blades.extend((int(x * 16), root, height, shade, rand(256), flower))

    if kind == "beach":
        # marram grass on the dune and round the palm's foot
        for x, root, count in ((30, 127, 6), (46, 127, 5), (PALM_AT[0] - 7, PALM_AT[1] + 2, 5), (PALM_AT[0] + 6, PALM_AT[1] + 3, 4), (124, 127, 5)):
            for i in range(count):
                blade(x + (i - count / 2) * 1.6 + frand(-0.5, 0.5), root + rand(2), 6 + rand(7), first if i % 2 else second)
    elif kind == "snow":
        # dry stalks poking through the snow
        for x, root in ((32, 127), (50, 124), (70, 127), (112, 126), (122, 121)):
            for i in range(2):
                blade(x + i * 2.6 + frand(-0.4, 0.4), root + rand(2), 3 + rand(5), first if i else second)
    else:
        # a fringe of long grass along the bottom, longer at the sides
        x = frand(0, 1.5)
        while x < 128:
            blade(x, 127 + rand(3), 5 + rand(7) + (3 if x < 20 or x > 110 else 0), first if rand(3) else second)
            x += frand(1.3, 2.3)
        # tufts round the tree's foot
        for i in range(6):
            blade(TREE_AT[0] - 6 + i * 2.4 + frand(-0.5, 0.5), TREE_AT[1] + 1 + rand(2), 3 + rand(4), second)
        if kind == "summer":
            # patches of flowers
            names = ("poppy", "daisy", "buttercup", "violet")
            for x, y, count in ((40, 108, 5), (66, 121, 6), (116, 108, 4)):
                for i in range(count):
                    blade(x + frand(-6, 6), y + rand(5), 3 + rand(3), first, SLOTS[names[(i + x) % 4]])
        elif kind == "spring":
            # more of them, daffodils, daisies and violets, and bigger patches
            names = ("buttercup", "daisy", "buttercup", "violet", "daisy")
            for x, y, count in ((14, 112, 5), (40, 106, 8), (62, 120, 8), (118, 108, 6), (30, 122, 5)):
                for i in range(count):
                    blade(x + frand(-8, 8), y + rand(6), 3 + rand(3), first, SLOTS[names[(i + x) % 5]])
        elif kind == "autumn":
            # fallen leaves lying under the tree and blown along the meadow
            for i in range(26):
                near = i < 16
                x = TREE_AT[0] + frand(-20, 22) if near else frand(4, 124)
                y = TREE_AT[1] + rand(5) - (1 if near else 0) + (0 if near else rand(8) - 8)
                blade(x, y, 1, second, SLOTS["blown%d" % (i % 3)])
    return array("i", blades)


# glints of frost or snow, on the meadow and the nearer hills
def sparkles(top, bottom, count):
    items = [0, 0]
    for _ in range(count):
        x = rand(124) + 2
        y = top + rand(bottom - top)
        items += [x + (8 if abs(x - TREE_AT[0]) < 4 else 0), y, rand(256), 120 + rand(200)]
    return array("i", items + [-1])


# each land's tree, blades and glints, made the first time the land shows. the
# seasons share a tree where they can, and colour it their own way. a theme can
# swap the tree, though the beach keeps its palm
SCENES = {}
TREES = {}
MAKERS = {"spring": leafy, "summer": leafy, "autumn": leafy, "winter": bare, "frost": bare, "snow": fir, "beach": palm}
THEME_TREES = {"christmas": fir, "halloween": bare}
# set by festive.py: called with the weather and the land once the land is
# drawn, to draw the day's things onto it
DRESS = None
# the tree standing now: which kind, and where its named nodes are in AT
standing = None
nodes_at = {}


def scene(kind, theme=None):
    global standing, nodes_at
    maker = MAKERS[kind]
    if kind != "beach":
        maker = THEME_TREES.get(theme, maker)
    if maker not in TREES:
        TREES[maker] = maker() + (_named,)
    standing = maker
    nodes_at = TREES[maker][2]
    if (kind, maker) not in SCENES:
        made = TREES[maker][:2] + (meadow(kind),)
        if kind == "beach":
            made += (glints(),)
        elif kind in ("frost", "snow"):
            made += (sparkles(90 if kind == "frost" else 82, 126, 16 if kind == "frost" else 22),)
        SCENES[kind, maker] = made
    return SCENES[kind, maker]


# leaves start spread across the screen, so they don't all arrive at once
for leaf in range(10):
    put(LEAVES, 4 + leaf * LEAF, (rand(2048), 960 + rand(1024), rand(256), 40 + rand(60), SLOTS["blown%d" % (leaf % 3)]))
LEAVES[3] = 12345


# ---- the wind ---------------------------------------------------------------------------

# the trunk bends up to MOST_BEND in a gale, and the wind turns the branches by
# up to MOST_TURN on top, both 1/16384 turn. GALE is the wind that does it
MOST_BEND = 2100
MOST_TURN = 2000
GALE = 80
TAU = 6.2832
WAVE_PERIOD = 6.0

# floats here hold about seven figures, so t soon grows too coarse to animate
# with. everything keeps its own clock instead, stepped by the time between
# frames and wrapped round. the step is smoothed, so a coarse t still moves
# things evenly
_then = None
_step = 0.033
_bend = 0.0
_bend_speed = 0.0
_blow = 0.0
# the branches' flutter, the grass's, ms for the sea and sparkles, the waves
# rolling in, and the phases of the slow swirls in the wind
_clock = 0.0
_grass_clock = 0.0
_ms = 0
_waves = 0.0
_swirls = [0.0, 2.1, 0.0]
SWIRL_RATES = (0.71, 1.73, 0.6)
# the gust blowing now: how far through it is, how long it lasts and how
# strong it gets, 0 to 1. then the wait for the next one
_gust = [1.0, 1.0, 0.0, 2.0]
# the steady wind the history was last filled for, and time to the next sample
_steady = None
_sample_in = 0.0
_speed = 0.0
_sign = 1


def _wind(w, t):
    global _then, _step, _bend, _bend_speed, _blow, _clock, _grass_clock, _ms, _waves, _steady, _sample_in, _speed, _sign
    step = 0.033 if _then is None else t - _then
    _then = t
    # t starts again from 0, or jumps after time off screen
    if step < 0 or step > 1:
        step = 0.033
    _step += (min(step, 0.25) - _step) * 0.15
    step = _step
    _ms = (_ms + int(step * 1000 + 0.5)) % (1 << 22)
    _waves = (_waves + step / WAVE_PERIOD) % 1
    swirls = _swirls
    for i in range(3):
        swirls[i] = (swirls[i] + step * SWIRL_RATES[i]) % TAU

    push = w["push"]
    speed = abs(push)
    sign = 1 if push >= 0 else -1
    _speed = speed
    _sign = sign

    # gusts come and go at random, each swelling and dying away over a few
    # seconds, more often the windier it is
    gust = _gust
    if gust[0] < 1:
        gust[0] += step / gust[1]
    else:
        gust[3] -= step
        if gust[3] <= 0:
            gust[0] = 0
            gust[1] = frand(1.2, 3.5)
            gust[2] = frand(0.35, 1.0)
            gust[3] = frand(1.5, 9 - min(6, speed / 10))
    surge = gust[2] * math.sin(math.pi * gust[0]) ** 2 if gust[0] < 1 else 0
    # and it never holds quite steady between them
    swirl = 0.65 * math.sin(swirls[0]) + 0.35 * math.sin(swirls[1])
    now = sign * (speed * (1 + 0.22 * swirl) + max(w["gust"] - speed, speed * 0.3) * surge)

    # the wind's history, 20 times a second. a gust crosses the screen in a
    # second or so, so the grass upwind bends first and the tree as it passes.
    # when the weather brings a new wind, it blows everywhere at once
    if _steady is None or abs(push - _steady) > 8:
        _steady = push
        for i in range(64):
            WIND[8 + i] = int(push * 16)
    _sample_in -= step
    while _sample_in <= 0:
        WIND[1] = (WIND[1] + 1) & 63
        WIND[8 + WIND[1]] = int(now * 16)
        _sample_in += 0.05
    reach = (1.6 - min(speed, 80) / 100) * 20 / 128
    WIND[2] = int(reach * 256)
    WIND[3] = 0 if sign > 0 else 1
    behind = int((TREE_AT[0] if sign > 0 else 127 - TREE_AT[0]) * reach)
    felt = WIND[8 + ((WIND[1] - behind) & 63)] / 16
    strength = abs(felt)

    # the trunk is a spring, pushed toward how far this wind would bend it and
    # damped so it sways back and forth a few times before it settles. stiffer
    # and quicker the windier it is. in still air it barely stirs
    target = MOST_BEND * min(1, (strength / GALE) ** 1.3)
    target = (target if felt >= 0 else -target) + 16 * math.sin(swirls[2])
    rate = TAU * (0.42 + min(speed, 90) / 200)
    _bend_speed += (rate * rate * (target - _bend) - 0.32 * rate * _bend_speed) * step
    _bend += _bend_speed * step
    # the branches and leaves follow the wind more closely
    _blow += (felt - _blow) * min(1, step * 6)
    turn = MOST_TURN * min(1, abs(_blow) / GALE) ** 1.1
    _clock = (_clock + step * (0.35 + min(strength, 80) / 35) * TURN) % (TURN * 16)
    MOTION[2] = int(_bend)
    MOTION[3] = int(turn if _blow >= 0 else -turn)
    MOTION[4] = int(256 * min(2, 0.12 + strength / 40))
    MOTION[5] = int(_clock)

    # grass flutters in ripples running downwind
    _grass_clock = (_grass_clock + step * (1.0 + min(strength, 80) / 25) * 256) % 256
    WIND[4] = int(10 + min(60, strength * 0.7))
    WIND[5] = int(_grass_clock)
    WIND[6] = -6 * sign


# ---- the layers -------------------------------------------------------------------------

_change = None
_key = None
_kind = "summer"
# the scene showing, from scene(), and how many times the land has been drawn
_scene = None
drawn = 0
_lighthouse = 0
# rain rings: the next slot to use
_ring = 0

GREY_SKIES = ("fog", "drizzle", "rain", "showers", "snow", "storm", "overcast")


# draws the land again when the scene or the light changes enough to see
def _light(w):
    global _change, _key, _kind, _day, _dusk, _dull, _wet, _lighthouse, _scene, drawn
    change = w["change"]
    if change == _change:
        return
    _change = change
    kind = w["land"]
    if kind not in MAKERS:
        kind = "summer"
    dull = min(1, max(0, (w["cloud"] - 35) / 65))
    if w["sky"] in GREY_SKIES:
        dull = max(dull, 1 if w["sky"] == "storm" else 0.75)
    wet = w["rain"] > 0
    theme = w.get("theme")
    key = (kind, wet, int(w["day"] * 16 + 0.5), int(w["dusk"] * 8 + 0.5), int(dull * 4 + 0.5), theme)
    if key == _key:
        return
    _key = key
    _kind = kind
    _wet = wet
    _day = key[2] / 16
    _dusk = key[3] / 8
    _dull = key[4] / 4
    made = _scene = scene(kind, theme)
    drawn += 1
    haze = sample(HORIZON - 2)
    high = sample(14)
    LAND_PIXELS[:HORIZON * 512] = CLEAR
    LAND.antialias = image.X4
    if kind == "beach":
        _lighthouse = coast(haze, high)
        SEA[9] = pack(tint((96, 196, 200), 0.8))
        SEA[10] = LUT[SLOTS["foam"]]
    else:
        country(kind, haze, high)
    palette(kind, theme)
    if DRESS is not None:
        DRESS(w, kind)
    base = PALM_AT if kind == "beach" else TREE_AT
    MOTION[0] = base[0] * 16
    MOTION[1] = base[1] * 16
    WIND[0] = len(made[2]) // BLADE
    RINGS[1] = LUT[SLOTS["ripple"]]
    if len(made) > 3 and kind != "beach":
        made[3][1] = pack(tint((255, 255, 255), 1)) if _day > 0.3 else pack((190, 210, 255))


# everything from the horizon down: the land as last drawn, then on the beach
# the sea's glints, waves and surf, and rain rings on the water
def land(w, t):
    global _ring
    _wind(w, t)
    _light(w)
    pixels = memoryview(screen)
    screen.blit(HEADLAND_BAND if _kind == "beach" else BAND, BAND_AT)
    pixels[HORIZON * 512:] = LAND_PIXELS[HORIZON * 512:]
    if _kind == "beach":
        SEA[0] = _ms
        # three waves roll in at a time, the nearest breaking on the sand as
        # the next sets out from the horizon. bigger the windier it is
        size = 0.6 + min(_speed, 60) / 100
        for wave in range(3):
            along = (_waves + wave / 3) % 1
            SEA[2 + wave * 2] = int((HORIZON + 3 + 18 * along ** 1.8) * 16)
            SEA[3 + wave * 2] = int(min(1, along * 6, (1 - along) * 12) * (50 + 110 * along) * size)
        surge = (_waves * 3) % 1
        run = surge / 0.3 if surge < 0.3 else (1 - (surge - 0.3) / 0.7) ** 1.5
        SEA[8] = int((5.5 * run * size - 0.5) * 16)
        sea(pixels, _scene[3], SEA, LUT)
        # the lighthouse shows its light after dark
        if _day < 0.5 and _ms % 4000 < 400:
            screen.pen = color.rgb(255, 236, 170)
            screen.rectangle(LIGHTHOUSE_X - 1, _lighthouse - 7, 3, 1)
    rain = w["rain"]
    if rain > 0 and _kind != "snow":
        RINGS[0] = 12
        RINGS[2] = 900
        RINGS[3] = _ms
        # a few rings a second for drizzle, many for a downpour
        if frand(0, 1) < rain * 4 * _step:
            at = 4 + _ring * RING
            _ring = (_ring + 1) % 12
            water = 3 if _kind == "beach" else rand(3)
            x, y, across, down = WATERS[water]
            put(RINGS, at, (x + int(frand(-0.7, 0.7) * min(across, 64)), int(y + frand(-0.6, 0.6) * down), _ms, water))
        rings(pixels, RINGS, LUT)


# the tree, swaying as the wind stepped in land() says
def tree(w, t):  # noqa: ARG001
    made = _scene
    pose(made[0], AT, MOTION, LUT)
    paint(memoryview(screen), made[1], AT, LUT)


# grass and flowers waving along the bottom, glints of frost or snow, and
# leaves blown across in a strong wind
def foreground(w, t):  # noqa: ARG001
    pixels = memoryview(screen)
    made = _scene
    grass(pixels, made[2], WIND, LUT)
    if _kind in ("frost", "snow"):
        made[3][0] = _ms
        sparkle(pixels, made[3], LUT)
    calm, fewest = LOOSE.get(_kind, (30, 0))
    if _kind in BLOWN and w["wind"] >= calm:
        LEAVES[0] = int(_step * 1000)
        LEAVES[1] = int(_sign * (20 + _speed * 0.9) * 16)
        LEAVES[2] = min(10, max(fewest, 2 + int((_speed - 25) / 7)))
        blow(pixels, LEAVES, LUT)
