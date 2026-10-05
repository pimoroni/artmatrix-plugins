import math
from random import choice, randint
import time
from bisect import insort

screen.antialias = image.X4

FRAME_TARGET = 40
last = None
show_bounds = False

grid = 8
cam_dist = 15
zoom = 180
yaw = 90  # left/right
pitch = 0   # up/down

yaw_sin = math.sin(math.radians(yaw))
yaw_cos = math.cos(math.radians(yaw))
pitch_sin = math.sin(math.radians(pitch))
pitch_cos = math.cos(math.radians(pitch))

SIZE = grid
half = SIZE / 2
centre = (grid - 1) / 2
NUM_PIPES = 2

cx = screen.width / 2
cy = screen.height / 2


PALETTE = [
    (1.0, 0.2, 0.2),   # red
    (0.2, 0.6, 1.0),   # blue
    (0.2, 1.0, 0.4),   # green
    (1.0, 0.8, 0.2),   # amber
    (0.9, 0.3, 1.0),   # magenta
    (0.2, 1.0, 1.0),   # cyan
    (1.0, 0.5, 0.1),   # orange
    (0.7, 0.7, 1.0),   # pale violet
]

HIGHLIGHT = color.rgb(255, 255, 255, 90)


corners = [
    (-half, -half, -half),
    (half, -half, -half),
    (half, half, -half),
    (-half, half, -half),
    (-half, -half, half),
    (half, -half, half),
    (half, half, half),
    (-half, half, half),
]

edges = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
]

directions = [(+1, 0, 0), (-1, 0, 0), (0, +1, 0), (0, -1, 0), (0, 0, +1), (0, 0, -1)]

used_cells = set()
render_list = []
pipes = []


def new_pipe(colour):
    pos = (randint(0, grid - 1), randint(0, grid - 1), randint(0, grid - 1))
    pipes.append([pos, choice(directions), transform_points(pos[0] - centre, pos[1] - centre, pos[2] - centre), colour])
    used_cells.add(pos)


def can_move(x, y, z):
    if not (0 <= x < grid and 0 <= y < grid and 0 <= z < grid):
        return False
    return (x, y, z) not in used_cells


def transform_points(x, y, z):

    rx = x * yaw_cos - z * yaw_sin
    rz = x * yaw_sin + z * yaw_cos

    ry = y * pitch_cos - rz * pitch_sin
    rz2 = y * pitch_sin + rz * pitch_cos

    depth = rz2 + cam_dist

    sx = cx + zoom * rx / depth
    sy = cy - zoom * ry / depth

    return sx, sy, depth


def step(pipe):

    last_dir = pipe[1]
    changed_dir = False

    # check if we can keep going in the direction we're currently heading in.
    hx, hy, hz = pipe[0]
    dx, dy, dz = pipe[1] if randint(0, 5) != 0 else choice(directions)
    next_cell = (hx + dx, hy + dy, hz + dz)
    valid = can_move(*next_cell)

    # if the moving in the same dir is not valid
    # pick one of the free directions at random
    if not valid:
        free = [d for d in directions if can_move(hx + d[0], hy + d[1], hz + d[2])]
        valid = bool(free)
        if valid:
            direction = choice(free)
            next_cell = (hx + direction[0], hy + direction[1], hz + direction[2])
            pipe[1] = direction
            pipe[0] = next_cell
    else:
        pipe[0] = next_cell
        pipe[1] = (dx, dy, dz)

    if valid:
        x, y, z = transform_points(next_cell[0] - centre, next_cell[1] - centre, next_cell[2] - centre)

        # grab  the previous values from used_cells instead of transforming again
        px, py, _ = pipe[2]

        changed_dir = (last_dir != pipe[1])

        alpha_norm = (z - SIZE / 4) / (cam_dist * 2 - SIZE)
        alpha = (1 - alpha_norm) * 255
        alpha = min(max(0, alpha), 255)

        # extend the highlight by a small amount
        ex = (x - px) * 0.10
        ey = (y - py) * 0.10

        r, g, b = pipe[3]
        colour = color.rgb(r * alpha, g * alpha, b * alpha)

        sort_key = (-z, x, y, next_cell)
        body = shape.line(vec2(x, y), vec2(px, py), 4)
        highlight = shape.line(vec2(px - 1 - ex, py - 1 - ey), vec2(x - 1 + ex, y - 1 + ey), 1)
        joint = (shape.circle(px, py, 4), shape.circle(px - 1, py - 1, 2)) if changed_dir else None
        cell = (colour, body, highlight, joint)

        used_cells.add(next_cell)
        insort(render_list, (sort_key, cell))
        pipe[2] = (x, y, z)

    # return whether or not a valid dir was found
    # if not, we'll create a new pipe in the update func
    return valid


points = []
for corner in corners:
    points.append(transform_points(*corner))

# create the initial pipes
for _ in range(NUM_PIPES):
    new_pipe(choice(PALETTE))


def update():
    global last

    if last is None or time.ticks_diff(time.ticks_ms(), last) >= FRAME_TARGET:
        last = time.ticks_ms()

        screen.pen = color.rgb(0, 0, 0)
        screen.clear()

        for pipe in pipes:
            if not step(pipe):
                used_cells.clear()
                render_list.clear()
                pipes.clear()
                for _ in range(NUM_PIPES):
                    new_pipe(choice(PALETTE))

        # store some of the functions locally for loop performance +.
        draw = screen.shape

        # drawing
        for _, (colour, body, highlight, joint) in render_list:
            screen.pen = colour
            draw(body)
            if joint:
                draw(joint[0])
                screen.pen = HIGHLIGHT
                draw(joint[1])

            # highlight colour
            screen.pen = HIGHLIGHT

            # draw the highlight
            draw(highlight)

        screen.pen = color.white
        # debug, showing the bounds
        if show_bounds:
            for edge in edges:
                c1, c2 = edge
                x1, y1, d1 = points[c1]
                x2, y2, d2 = points[c2]
                screen.line(x1, y1, x2, y2)
