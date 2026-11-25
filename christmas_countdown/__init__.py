import math
import random
import time

import timezones

WIDTH = const(128)
HEIGHT = const(128)

# what's in each cell of the snow grid
EMPTY = const(0)
SOLID = const(1)  # letters and the ground
SNOW = const(2)

# the letters go between the lights and the ground
TEXT_TOP = 24
TEXT_BOTTOM = 120
LINE_GAP = 8
CHRISTMAS_LINE_GAP = 6
# the number is scaled up by whole pixels to fill about this much
NUMBER_WIDTH = 110
NUMBER_HEIGHT = 66
MAX_NUMBER_SCALE = 4

NUMBER_FONT = font.ignore
WORD_FONT = font.smart

# (r, g, b)
SKY_TOP = (4, 8, 22)
SKY_BOTTOM = (24, 40, 78)
RED_STRIPE = (214, 28, 40)
WHITE_STRIPE = (250, 246, 240)
WORD_COLOUR = (255, 255, 255)
GROUND_COLOUR = (228, 236, 255)
SNOW_TOP_COLOUR = (255, 255, 255)
SNOW_UNDER_COLOUR = (201, 214, 242)
WIRE_COLOUR = (22, 61, 34)
STAR_COLOUR = (150, 155, 175)
# letter edges facing the light are this much brighter, the far edges darker. x256
EDGE_LIGHT = 287
EDGE_DARK = 184
# a shadow keeps this much of what's under it. x256
SHADOW_KEEP = 115
SHADOW_OFFSET = 2

# fairy lights hang in two swags along the top
BULBS = 16
FIRST_BULB_X = 4
BULB_SPACING = 8
SWAG_WIDTH = 64
SWAG_DROP = 11
WIRE_TOP = 3
# each bulb hangs a pixel under the wire
BULB_TOP = WIRE_TOP + 1
BULB_COLOURS = (
    (255, 59, 48),  # red
    (255, 204, 0),  # yellow
    (52, 199, 89),  # green
    (10, 132, 255),  # blue
    (255, 45, 149),  # pink
    (255, 149, 0),  # orange
)
# bulbs fade between DIMMEST_BULB and full, TWINKLE_MS ms a radian.
# neighbours are TWINKLE_STAGGER radians apart
DIMMEST_BULB = 0.5
TWINKLE_MS = 400
TWINKLE_STAGGER = 1.9
BULB_PLACES = []
for bulb in range(BULBS):
    bulb_x = FIRST_BULB_X + bulb * BULB_SPACING
    along_swag = (bulb_x % SWAG_WIDTH) / SWAG_WIDTH
    sag = SWAG_DROP * math.sin(math.pi * along_swag)
    BULB_PLACES.append((bulb_x, round(BULB_TOP + sag)))

# the halos round the letters and lights are baked in once
BLOOM_THRESHOLD = 170
BLOOM_INTENSITY = 120
BLOOM_RADIUS = 3

# snow, in thousandths of a pixel
MILLI = 1000
SNOWFALL = 45  # flakes a second
# flake speeds are thousandths of a pixel a ms, which is px a second
SLOWEST_FLAKE = 14
FASTEST_FLAKE = 26
# each flake sidesteps one pixel every this many rows
DRIFT_ROWS = 7
# rows above SETTLE_TOP are among the lights. flakes melt there, or on snow MAX_DEPTH deep
SETTLE_TOP = 22
MAX_DEPTH = 3
GROUND_TOP = 125
# the ground rises and falls a pixel, over this many px a radian
GROUND_WAVE = 9
STARS = 40

# far flakes fall behind the letters and never land
FAR_FLAKES = 40
FAR_FLAKE = color.rgb(200, 215, 255, 90)
far_x = [random.randrange(WIDTH) for _ in range(FAR_FLAKES)]
far_y = [random.randrange(HEIGHT * MILLI) for _ in range(FAR_FLAKES)]
# px a second
SLOWEST_FAR_FLAKE = 6
FASTEST_FAR_FLAKE = 10
far_speed = [random.randint(SLOWEST_FAR_FLAKE, FASTEST_FAR_FLAKE) for _ in range(FAR_FLAKES)]
# near flakes are big and soft, in front of everything
NEAR_FLAKES = 9
NEAR_FLAKE = color.rgb(255, 255, 255, 140)
near_x = [random.randrange(WIDTH) for _ in range(NEAR_FLAKES)]
near_y = [random.randrange(HEIGHT * MILLI) for _ in range(NEAR_FLAKES)]
# px a second
SLOWEST_NEAR_FLAKE = 22
FASTEST_NEAR_FLAKE = 38
near_speed = [random.randint(SLOWEST_NEAR_FLAKE, FASTEST_NEAR_FLAKE) for _ in range(NEAR_FLAKES)]
FLAKE = color.rgb(255, 255, 255)

# an unset clock starts in 2021
EARLIEST_YEAR = 2025
SECONDS_A_DAY = 86400
# a long frame would make the snow jump
LONGEST_STEP_MS = 100

# everything that doesn't move, with settled snow painted in as it lands
backdrop = image(WIDTH, HEIGHT)
# four bytes a pixel, red first
backdrop_pixels = memoryview(backdrop)
# text is drawn here first to find which pixels it covers
stencil = image(WIDTH, HEIGHT)
stencil_pixels = memoryview(stencil)

cells = bytearray(WIDTH * HEIGHT)
# each falling flake is [x, y in thousandths, speed, sidestep, row it sidesteps on]
flakes = []
flakes_owed = 0

shown_date = None
last_frame = time.ticks_ms()


def update():
    global shown_date, last_frame, flakes, flakes_owed

    now = time.ticks_ms()
    step = min(time.ticks_diff(now, last_frame), LONGEST_STEP_MS)
    last_frame = now

    year, month, day = timezones.localtime()[:3]
    if (year, month, day) != shown_date:
        shown_date = (year, month, day)

        # after the 25th it counts to next year's
        christmas_year = year + 1 if month == 12 and day > 25 else year
        today = time.mktime((year, month, day, 0, 0, 0, 0, 0))
        sleeps = (time.mktime((christmas_year, 12, 25, 0, 0, 0, 0, 0)) - today) // SECONDS_A_DAY

        clock_set = year >= EARLIEST_YEAR
        christmas_day = clock_set and sleeps == 0

        # (text, font, candy stripes or plain)
        if not clock_set:
            lines = ()
        elif christmas_day:
            lines = (("Merry", NUMBER_FONT, True), ("Christmas!", NUMBER_FONT, True))
        else:
            lines = ((str(sleeps), NUMBER_FONT, True), ("sleep" if sleeps == 1 else "sleeps", WORD_FONT, False))
        line_gap = CHRISTMAS_LINE_GAP if christmas_day else LINE_GAP

        # each line as [inked (x, y) from its top left, ink width, ink height, scale, stripes]
        shapes = []
        for words, face, stripes in lines:
            stencil.pen = color.rgb(0, 0, 0)
            stencil.clear()
            stencil.pen = color.rgb(255, 255, 255)
            stencil.font = face
            stencil.text(words, 0, 0)
            box_width, box_height = stencil.measure_text(words)
            inked = []
            for y in range(min(int(box_height), HEIGHT)):
                for x in range(min(int(box_width), WIDTH)):
                    if stencil_pixels[(y * WIDTH + x) * 4]:
                        inked.append((x, y))
            left = min(x for x, _ in inked)
            top = min(y for _, y in inked)
            ink_width = max(x for x, _ in inked) - left + 1
            ink_height = max(y for _, y in inked) - top + 1
            # only the countdown number is scaled up
            scale = 1
            if stripes and not christmas_day:
                scale = max(1, min(MAX_NUMBER_SCALE, NUMBER_WIDTH // ink_width, NUMBER_HEIGHT // ink_height))
            shapes.append(([(x - left, y - top) for x, y in inked], ink_width, ink_height, scale, stripes))

        backdrop.pen = brush.gradient(brush.LINEAR, 0, 0, 0, HEIGHT - 1, [(0, color.rgb(*SKY_TOP)), (1, color.rgb(*SKY_BOTTOM))])
        backdrop.clear()

        cells[:] = bytes(WIDTH * HEIGHT)
        flakes = []

        backdrop.pen = color.rgb(*WIRE_COLOUR)
        for x in range(WIDTH):
            sag = SWAG_DROP * math.sin(math.pi * (x % SWAG_WIDTH) / SWAG_WIDTH)
            backdrop.rectangle(x, round(WIRE_TOP + sag), 1, 1)
        for bulb, (bulb_x, bulb_y) in enumerate(BULB_PLACES):
            backdrop.pen = color.rgb(*BULB_COLOURS[bulb % len(BULB_COLOURS)])
            backdrop.rectangle(bulb_x - 1, bulb_y, 3, 2)

        # the lines stack in the middle of the space under the lights
        stack_height = sum(height * scale for _, _, height, scale, _ in shapes) + line_gap * (len(shapes) - 1)
        line_top = TEXT_TOP + (TEXT_BOTTOM - TEXT_TOP - stack_height) // 2
        placed = []
        for inked, ink_width, ink_height, scale, stripes in shapes:
            line_left = (WIDTH - ink_width * scale) // 2
            pixels = []
            for x, y in inked:
                for down in range(scale):
                    for across in range(scale):
                        pixels.append((line_left + x * scale + across, line_top + y * scale + down))
            for x, y in pixels:
                cells[y * WIDTH + x] = SOLID
            placed.append((pixels, scale, stripes))
            line_top += ink_height * scale + line_gap

        for pixels, _, _ in placed:
            for x, y in pixels:
                shadow_x = x + SHADOW_OFFSET
                shadow_y = y + SHADOW_OFFSET
                if shadow_x < WIDTH and shadow_y < HEIGHT and not cells[shadow_y * WIDTH + shadow_x]:
                    at = (shadow_y * WIDTH + shadow_x) * 4
                    for channel in range(3):
                        backdrop_pixels[at + channel] = backdrop_pixels[at + channel] * SHADOW_KEEP >> 8

        for pixels, scale, stripes in placed:
            # stripes are 4 px wide on big letters, 2 on small ones
            stripe_width = 4 if scale > 1 else 2
            for x, y in pixels:
                if not stripes:
                    colour = WORD_COLOUR
                else:
                    colour = WHITE_STRIPE if (x + y) // stripe_width % 2 else RED_STRIPE
                    lit_edge = not cells[(y - 1) * WIDTH + x] or not cells[y * WIDTH + x - 1]
                    far_edge = x + 1 < WIDTH and y + 1 < HEIGHT and not cells[(y + 1) * WIDTH + x + 1]
                    if lit_edge:
                        colour = [min(255, channel * EDGE_LIGHT >> 8) for channel in colour]
                    elif far_edge:
                        colour = [channel * EDGE_DARK >> 8 for channel in colour]
                at = (y * WIDTH + x) * 4
                backdrop_pixels[at] = colour[0]
                backdrop_pixels[at + 1] = colour[1]
                backdrop_pixels[at + 2] = colour[2]

        backdrop.bloom(BLOOM_THRESHOLD, BLOOM_INTENSITY, BLOOM_RADIUS)

        # stars go on after the bloom so they stay sharp
        backdrop.pen = color.rgb(*STAR_COLOUR)
        for _ in range(STARS):
            star_x = random.randrange(WIDTH)
            star_y = random.randrange(HEIGHT)
            if not cells[star_y * WIDTH + star_x]:
                backdrop.rectangle(star_x, star_y, 1, 1)

        backdrop.pen = color.rgb(*GROUND_COLOUR)
        for x in range(WIDTH):
            ground = GROUND_TOP + round(math.sin(x / GROUND_WAVE))
            backdrop.vspan(x, ground, HEIGHT - ground)
            for y in range(ground, HEIGHT):
                cells[y * WIDTH + x] = SOLID

    screen.blit(backdrop, 0, 0)

    screen.pen = FAR_FLAKE
    for i in range(FAR_FLAKES):
        far_y[i] = (far_y[i] + far_speed[i] * step) % (HEIGHT * MILLI)
        y = far_y[i] // MILLI
        if not cells[y * WIDTH + far_x[i]]:
            screen.rectangle(far_x[i], y, 1, 1)

    flakes_owed += SNOWFALL * step
    while flakes_owed >= MILLI:
        flakes_owed -= MILLI
        start_x = random.randrange(WIDTH)
        speed = random.randint(SLOWEST_FLAKE, FASTEST_FLAKE)
        sidestep = random.choice((-1, 1))
        sidestep_row = random.randrange(DRIFT_ROWS)
        flakes.append([start_x, 0, speed, sidestep, sidestep_row])

    # flakes fall a row at a time. one that hits something slides off sideways, or settles
    still_falling = []
    screen.pen = FLAKE
    for flake in flakes:
        x, y_milli, speed, sidestep, sidestep_row = flake
        row = y_milli // MILLI
        y_milli += speed * step
        landed = False
        while row < y_milli // MILLI:
            below = row + 1
            if not cells[below * WIDTH + x]:
                row = below
                if row % DRIFT_ROWS == sidestep_row and 0 <= x + sidestep < WIDTH and not cells[row * WIDTH + x + sidestep]:
                    x += sidestep
                continue
            if 0 <= x + sidestep < WIDTH and not cells[row * WIDTH + x + sidestep] and not cells[below * WIDTH + x + sidestep]:
                x += sidestep
                continue
            if 0 <= x - sidestep < WIDTH and not cells[row * WIDTH + x - sidestep] and not cells[below * WIDTH + x - sidestep]:
                x -= sidestep
                continue

            depth = 0
            while depth < MAX_DEPTH and cells[(below + depth) * WIDTH + x] == SNOW:
                depth += 1
            if row >= SETTLE_TOP and depth < MAX_DEPTH:
                cells[row * WIDTH + x] = SNOW
                at = (row * WIDTH + x) * 4
                backdrop_pixels[at] = SNOW_TOP_COLOUR[0]
                backdrop_pixels[at + 1] = SNOW_TOP_COLOUR[1]
                backdrop_pixels[at + 2] = SNOW_TOP_COLOUR[2]
                if depth:
                    at = (below * WIDTH + x) * 4
                    backdrop_pixels[at] = SNOW_UNDER_COLOUR[0]
                    backdrop_pixels[at + 1] = SNOW_UNDER_COLOUR[1]
                    backdrop_pixels[at + 2] = SNOW_UNDER_COLOUR[2]
            landed = True
            break
        if landed:
            continue
        flake[0] = x
        flake[1] = y_milli
        still_falling.append(flake)
        screen.rectangle(x, row, 1, 1)
    flakes = still_falling

    for bulb, (bulb_x, bulb_y) in enumerate(BULB_PLACES):
        wave = math.sin(now / TWINKLE_MS + bulb * TWINKLE_STAGGER)
        glow = DIMMEST_BULB + (1 - DIMMEST_BULB) * (wave + 1) / 2
        red, green, blue = BULB_COLOURS[bulb % len(BULB_COLOURS)]
        screen.pen = color.rgb(int(red * glow), int(green * glow), int(blue * glow))
        screen.rectangle(bulb_x - 1, bulb_y, 3, 2)
        screen.rectangle(bulb_x, bulb_y + 2, 1, 1)

    screen.pen = NEAR_FLAKE
    for i in range(NEAR_FLAKES):
        near_y[i] += near_speed[i] * step
        if near_y[i] >= HEIGHT * MILLI:
            near_y[i] -= HEIGHT * MILLI
            near_x[i] = random.randrange(WIDTH)
        screen.rectangle(near_x[i], near_y[i] // MILLI, 2, 2)
