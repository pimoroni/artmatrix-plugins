import math
from random import choice, randint
import time
from bisect import insort

screen.antialias = image.X4

FRAME_TARGET = 40
last = None

grid = 8
cam_dist = 15
zoom = 180
yaw = 90  # left/right
pitch = 0   # up/down

yaw_sin = math.sin(math.radians(yaw))
yaw_cos = math.cos(math.radians(yaw))
pitch_sin = math.sin(math.radians(pitch))
pitch_cos = math.cos(math.radians(pitch))

centre = (grid - 1) / 2
NUM_PIPES = 2

# how far the front and back of the grid are from the camera, for dimming
near_depth = cam_dist - centre
far_depth = cam_dist + centre
FRONT_BRIGHTNESS = 0.8  # nearest pipes
BACK_BRIGHTNESS = 0.28  # furthest pipes
SHADOW_BRIGHTNESS = 0.5  # shadow edge, as a share of the pipe's own brightness

FULL_CELLS = int(grid ** 3 * 0.5)  # fade out and start again once this many cells are used
FADE_MS = 1000
FADE_PEN = color.rgb(0, 0, 0, 40)  # drawn over the last frame each step, so it builds up
fade_started = None  # ticks_ms when the fade began, None while pipes are growing

screen_centre_x = screen.width / 2
screen_centre_y = screen.height / 2

# depths closer than this count as level, float sin/cos never quite give 0
SAME_DEPTH = 0.01
TURN_ODDS = 6  # one step in this many heads off in a random direction
PIPE_WIDTH = 4
JOINT_RADIUS = 4


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


directions = [(+1, 0, 0), (-1, 0, 0), (0, +1, 0), (0, -1, 0), (0, 0, +1), (0, 0, -1)]

used_cells = set()
render_list = []
pipes = []


def new_pipe():
    taken = [pipe[3] for pipe in pipes]
    colour = choice([palette_colour for palette_colour in PALETTE if palette_colour not in taken])
    while True:
        pos = (randint(0, grid - 1), randint(0, grid - 1), randint(0, grid - 1))
        if pos not in used_cells:
            break
    used_cells.add(pos)
    # a pipe is [head cell, direction, head's (screen x, screen y, depth), colour, current run]
    # a run is (start x, start y, depth, its render_list cell), None until the first step
    return [pos, choice(directions), transform_points(pos[0] - centre, pos[1] - centre, pos[2] - centre), colour, None]


def can_move(x, y, z):
    if not (0 <= x < grid and 0 <= y < grid and 0 <= z < grid):
        return False
    return (x, y, z) not in used_cells


def transform_points(x, y, z):

    yawed_x = x * yaw_cos - z * yaw_sin
    yawed_z = x * yaw_sin + z * yaw_cos

    pitched_y = y * pitch_cos - yawed_z * pitch_sin
    pitched_z = y * pitch_sin + yawed_z * pitch_cos

    depth = pitched_z + cam_dist

    screen_x = screen_centre_x + zoom * yawed_x / depth
    screen_y = screen_centre_y - zoom * pitched_y / depth

    return screen_x, screen_y, depth


def step(pipe):

    last_dir = pipe[1]

    # carry on the way the pipe's heading, apart from the odd random turn
    head_x, head_y, head_z = pipe[0]
    step_x, step_y, step_z = pipe[1] if randint(0, TURN_ODDS - 1) != 0 else choice(directions)
    next_cell = (head_x + step_x, head_y + step_y, head_z + step_z)
    valid = can_move(*next_cell)

    # that cell's taken or off the grid, so pick one of the free directions at random
    if not valid:
        free = [direction for direction in directions if can_move(head_x + direction[0], head_y + direction[1], head_z + direction[2])]
        valid = bool(free)
        if valid:
            direction = choice(free)
            next_cell = (head_x + direction[0], head_y + direction[1], head_z + direction[2])
            pipe[1] = direction
            pipe[0] = next_cell
    else:
        pipe[0] = next_cell
        pipe[1] = (step_x, step_y, step_z)

    if valid:
        screen_x, screen_y, depth = transform_points(next_cell[0] - centre, next_cell[1] - centre, next_cell[2] - centre)

        # reuse the previous point instead of transforming it again
        prev_x, prev_y, _ = pipe[2]

        changed_dir = (last_dir != pipe[1])

        depth_norm = (depth - near_depth) / (far_depth - near_depth)
        brightness = (FRONT_BRIGHTNESS - depth_norm * (FRONT_BRIGHTNESS - BACK_BRIGHTNESS)) * 255
        brightness = min(max(0, brightness), 255)

        # highlight and shadow sit 1px off the middle, so they stop short of the joint ball.
        # stretch them 10% of one cell past each end of the run to close the gap
        overhang_x = (screen_x - prev_x) * 0.10
        overhang_y = (screen_y - prev_y) * 0.10

        # segments drawn end to end leave a seam or a bump at every join, so a pipe going
        # straight on at the same depth stretches its current run instead of adding a segment
        run = pipe[4]
        if not changed_dir and run is not None and abs(depth - run[2]) < SAME_DEPTH:
            start_x, start_y, _, cell = run
        else:
            start_x, start_y = prev_x, prev_y

            red, green, blue = pipe[3]
            colour = color.rgb(red * brightness, green * brightness, blue * brightness)
            shade = brightness * SHADOW_BRIGHTNESS
            shadow_colour = color.rgb(red * shade, green * shade, blue * shade)

            # (shadow ball, body ball nudged up left so a dark crescent shows, highlight)
            # on every turn, and on the first step so the pipe starts with a ball
            joint = None
            if changed_dir or run is None:
                joint = (shape.circle(prev_x, prev_y, JOINT_RADIUS),
                         shape.circle(prev_x - 0.5, prev_y - 0.5, JOINT_RADIUS - 0.5),
                         shape.circle(prev_x - 1, prev_y - 1, JOINT_RADIUS / 2))

            # [colour, shadow colour, body, shadow, highlight, joint], lines filled in below
            cell = [colour, shadow_colour, None, None, None, joint]
            # next_cell breaks depth ties, so insort never has to compare the cells
            insort(render_list, ((-depth, next_cell), cell))
            pipe[4] = (start_x, start_y, depth, cell)

        cell[2] = shape.line(vec2(start_x, start_y), vec2(screen_x, screen_y), PIPE_WIDTH)
        # light comes from the top left, so the shadow sits opposite the highlight
        cell[3] = shape.line(vec2(start_x + 1 - overhang_x, start_y + 1 - overhang_y), vec2(screen_x + 1 + overhang_x, screen_y + 1 + overhang_y), 1)
        cell[4] = shape.line(vec2(start_x - 1 - overhang_x, start_y - 1 - overhang_y), vec2(screen_x - 1 + overhang_x, screen_y - 1 + overhang_y), 1)

        used_cells.add(next_cell)
        pipe[2] = (screen_x, screen_y, depth)

    # return whether or not a valid dir was found
    # if not, we'll create a new pipe in the update func
    return valid


# create the initial pipes
for _ in range(NUM_PIPES):
    pipes.append(new_pipe())


def update():
    global last, fade_started

    if last is None or time.ticks_diff(time.ticks_ms(), last) >= FRAME_TARGET:
        last = time.ticks_ms()

        # grid's full, so darken what's on screen a bit more each step, then start again
        if fade_started is not None:
            if time.ticks_diff(last, fade_started) < FADE_MS:
                screen.pen = FADE_PEN
                screen.clear()
                return
            fade_started = None
            used_cells.clear()
            render_list.clear()
            pipes.clear()
            for _ in range(NUM_PIPES):
                pipes.append(new_pipe())

        screen.pen = color.rgb(0, 0, 0)
        screen.clear()

        # a boxed in pipe stops where it is and a new one starts somewhere free
        for index, pipe in enumerate(pipes):
            if not step(pipe):
                pipes[index] = new_pipe()

        if len(used_cells) >= FULL_CELLS:
            fade_started = last

        # a local is quicker to look up than screen.shape in the loop
        draw = screen.shape

        for _, (colour, shadow_colour, body, shadow, highlight, joint) in render_list:
            screen.pen = colour
            draw(body)
            screen.pen = shadow_colour
            draw(shadow)
            if joint:
                draw(joint[0])
                screen.pen = colour
                draw(joint[1])
                screen.pen = HIGHLIGHT
                draw(joint[2])

            screen.pen = HIGHLIGHT
            draw(highlight)
