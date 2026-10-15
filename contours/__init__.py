import time
import micropython
from array import array
from micropython import const
from random import randrange

from plugin_config import plugin_config

# map size is 128 pixels across, reading this many table cells x256
ZOOM = const(48)
# lines from bottom to top
LEVELS = const(10)

# ground, then line colours from low to high. top stop held back as full white is too much
PRESETS = {
    "amber": [(0, 0, 0), (90, 40, 8), (170, 90, 20), (230, 160, 50), (240, 210, 130)],
    "sea": [(0, 0, 2), (10, 40, 110), (20, 100, 180), (40, 180, 220), (170, 230, 235)],
    "moss": [(0, 1, 0), (30, 70, 10), (70, 140, 20), (140, 200, 40), (210, 235, 140)],
    "neon": [(1, 0, 2), (80, 20, 140), (160, 30, 170), (230, 60, 160), (250, 170, 210)],
    "mono": [(0, 0, 0), (60, 60, 60), (110, 110, 110), (160, 160, 160), (210, 210, 210)],
}

cfg = plugin_config("contours", {
    "style": "lines",  # lines, or solid for flat bands with no lines
    "scheme": "amber",  # one of PRESETS
    "speed": 2,  # 1 slow, 2 medium, 4 fast
})
style = cfg["style"]
scheme = cfg["scheme"]
speed = cfg["speed"]

STOPS = PRESETS.get(scheme, PRESETS["amber"])
SPACING = 65536 // LEVELS
# solid tops from 65% of the way up
FILL_FROM = 65536 * 65 // 100

red, green, blue = STOPS[0]
GROUND = 0xff000000 | (blue << 16) | (green << 8) | red

# packed like the screen stores a pixel: 0xaabbggrr
# 0-255 lines by height, 256-511 every 5th line at full brightness, 512 on each band's fill
PALETTE = array("I", [0] * (512 + LEVELS + 7))
# fill colour by the height of a band's bottom edge. TERRACE is the same for the solid style
FILL = [GROUND] * 256
TERRACE = [GROUND] * 256
for i in range(256):
    # line colours run through stops 1-4
    along = i * 3 / 255
    stop = min(int(along), 2) + 1
    into_stop = along - stop + 1
    low = STOPS[stop]
    high = STOPS[stop + 1]
    red = int(low[0] + (high[0] - low[0]) * into_stop)
    green = int(low[1] + (high[1] - low[1]) * into_stop)
    blue = int(low[2] + (high[2] - low[2]) * into_stop)
    PALETTE[i + 256] = 0xff000000 | (blue << 16) | (green << 8) | red
    # the rest sit back a bit, like a walking map
    PALETTE[i] = 0xff000000 | ((blue * 9 // 16) << 16) | ((green * 9 // 16) << 8) | (red * 9 // 16)

    # fades in over one band below the start, then 25% up to 45% at the top
    fade = (i * 256 - FILL_FROM + SPACING) / SPACING
    if fade > 0:
        shade = min(fade, 1) * (0.25 + 0.2 * max(i * 256 - FILL_FROM, 0) / (65536 - FILL_FROM))
        FILL[i] = 0xff000000 | (int(blue * shade) << 16) | (int(green * shade) << 8) | int(red * shade)

    # dark valleys up to line brightness on top. brighter would be a lot of light
    shade = 0.15 + 0.41 * i / 255
    TERRACE[i] = 0xff000000 | (int(blue * shade) << 16) | (int(green * shade) << 8) | int(red * shade)

BIG_HILLS = [randrange(256) for _ in range(64)]
SMALL_HILLS = [randrange(256) for _ in range(256)]

# catmull-rom from start to end. it keeps the slope going through each post.
# easing goes flat at posts and left straight creases along x and y
def curve(before, start, end, after, into):
    return start + 0.5 * into * (
        end - before + into * (
            2 * before - 5 * start + 4 * end - after + into * (
                3 * (start - end) + after - before)))

def blend(posts, spacing, x, y):
    posts_across = 64 // spacing
    post_x = x // spacing
    post_y = y // spacing
    into_x = (x % spacing) / spacing
    into_y = (y % spacing) / spacing

    # four posts each way around the spot
    rows = []
    for step in (-1, 0, 1, 2):
        row = ((post_y + step) % posts_across) * posts_across
        before = posts[row + (post_x - 1) % posts_across]
        start = posts[row + post_x]
        end = posts[row + (post_x + 1) % posts_across]
        after = posts[row + (post_x + 2) % posts_across]
        rows.append(curve(before, start, end, after, into_x))
    return curve(rows[0], rows[1], rows[2], rows[3], into_y)

# big hills plus a little wiggle on top, so the rings aren't plain ovals
heights = []
for i in range(64 * 64):
    x = i & 63
    y = i >> 6
    heights.append(blend(BIG_HILLS, 8, x, y) + blend(SMALL_HILLS, 4, x, y) / 2)

# stretch to fill 0-65535. 16 bit so lines don't wobble on gentle slopes
lo = min(heights)
hi = max(heights)
CLOUD = array("H", [int((h - lo) * 65535 / (hi - lo)) for h in heights])
del heights

# viper takes four args max, so these ride together.
# drift x and y, rise, solid. 8 on the last three rows
PARAMS = array("i", [0] * (8 + 3 * 128))
PARAMS[3] = style == "solid"


# one four-cell read a pixel at full 128x128. positions x256 (>> 8 cell, & 255 how far in).
# value is height x levels, so each line sits on a multiple of 65536
@micropython.viper
def contours(cloud: ptr16, pixels: ptr32, pal: ptr32, params: ptr32):  # noqa: F821
    drift_x = int(params[0])
    drift_y = int(params[1])
    rise = int(params[2])
    solid = int(params[3])
    # int() so it isn't folded into a big int before viper sees it
    opaque = int(255) << 24
    for y in range(129):
        if y < 128:
            read_y = y * ZOOM + drift_y
            cell_y = (read_y >> 8) & 63
            into_y = read_y & 255
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            store = 8 + (y % 3) * 128
            for x in range(128):
                read_x = x * ZOOM + drift_x
                cell_x = (read_x >> 8) & 63
                into_x = read_x & 255
                next_x = (cell_x + 1) & 63
                top_left = int(cloud[cell_x + row])
                top_right = int(cloud[next_x + row])
                bottom_left = int(cloud[cell_x + next_row])
                bottom_right = int(cloud[next_x + next_row])
                top = top_left + (((top_right - top_left) * into_x) >> 8)
                bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
                height = top + (((bottom - top) * into_y) >> 8)
                params[store + x] = (height + rise) * LEVELS

        # rows are read one ahead of drawing so a pixel can see the one below it
        if y == 0:
            continue

        # draw the row before. edges look at themselves where there's no neighbour
        draw_y = y - 1
        here = 8 + (draw_y % 3) * 128
        # slopes are halved when they span two rows. edges span one
        rows_apart = 0
        above = here
        if draw_y > 0:
            above = 8 + ((draw_y + 2) % 3) * 128
            rows_apart += 1
        below = here
        if draw_y < 127:
            below = 8 + (y % 3) * 128
            rows_apart += 1
        for x in range(128):
            value = int(params[here + x])
            band = value >> 16
            x_left = x
            if x > 0:
                x_left = x - 1
            x_right = x
            if x < 127:
                x_right = x + 1

            # slope per pixel, looking both ways so ridges don't look steep.
            # max + 3/8 min is near enough its length
            across = int(params[here + x_right]) - int(params[here + x_left])
            if x_right - x_left == 2:
                across = across >> 1
            if across < 0:
                across = -across
            down = int(params[below + x]) - int(params[above + x])
            if rows_apart == 2:
                down = down >> 1
            if down < 0:
                down = -down
            if across > down:
                steepness = across + ((down * 3) >> 3)
            else:
                steepness = down + ((across * 3) >> 3)

            # nearest line is this band's bottom or the next one's
            into_band = value & 0xffff
            if into_band < 32768:
                gap = into_band
                nearest = band
            else:
                gap = 65536 - into_band
                nearest = band + 1

            # colour shows cover/256 of itself over under
            colour = pal[band + 512]
            under = colour
            cover = 256
            if solid:
                # no line. within half a pixel of a level, mix with the band across it
                if gap * 2 < steepness:
                    across_band = band + 1
                    if into_band < 32768:
                        # nothing below band 0, so it mixes with itself
                        across_band = band
                        if band > 0:
                            across_band = band - 1
                    under = pal[across_band + 512]
                    cover = 128 + (gap << 8) // steepness
            else:
                # 2 px line plus a pixel of soft edge
                reach = steepness * 3
                if gap * 2 < reach:
                    shade = (value // LEVELS - rise) >> 8
                    if nearest % 5 == 0:
                        colour = pal[shade + 256]
                    else:
                        colour = pal[shade]
                    cover = ((reach - gap * 2) << 7) // steepness

            if cover < 256:
                red = ((colour & 255) * cover + (under & 255) * (256 - cover)) >> 8
                green = (((colour >> 8) & 255) * cover + ((under >> 8) & 255) * (256 - cover)) >> 8
                blue = (((colour >> 16) & 255) * cover + ((under >> 16) & 255) * (256 - cover)) >> 8
                colour = opaque | (blue << 16) | (green << 8) | red
            pixels[x + (draw_y << 7)] = colour


def update():
    now = time.ticks_ms()
    # speed 2 drifts ~0.5 cells a second, whatever the frame rate
    PARAMS[0] = now * speed // 16
    PARAMS[1] = now * speed // 40
    # one level every 3 s at speed 2. counts down so rings shrink uphill.
    # wraps every 5 levels so bright lines stay bright. 30 s suits every speed
    rise = 5 * SPACING - ((now % 30000) * speed * SPACING // 6000) % (5 * SPACING)
    PARAMS[2] = rise
    # band colour follows its bottom edge, so it changes smoothly as it climbs.
    # one band spare as solid edges look one up
    for band in range(LEVELS + 7):
        bottom = band * SPACING - rise
        if style == "solid":
            PALETTE[band + 512] = TERRACE[min(max(bottom >> 8, 0), 255)]
        else:
            PALETTE[band + 512] = FILL[min(bottom >> 8, 255)] if bottom >= 0 else GROUND
    contours(CLOUD, memoryview(screen), PALETTE, PARAMS)
