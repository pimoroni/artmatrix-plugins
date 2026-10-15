import time
import micropython
from array import array
from random import randrange

from plugin_config import plugin_config

WIDTH = screen.width // 2
HEIGHT = screen.height // 2
BLOCK_SIZE = 2

# dark to bright, top stop held back as full white is too much on the panel
PRESETS = {
    "ocean": [(2, 10, 36), (12, 64, 160), (60, 150, 235), (160, 190, 220)],
    "lava": [(0, 0, 0), (110, 8, 6), (230, 90, 10), (240, 190, 60)],
    "aurora": [(20, 6, 45), (150, 25, 120), (30, 180, 90), (150, 220, 180)],
    "marble": [(10, 16, 48), (70, 92, 140), (190, 180, 160), (215, 210, 200)],
    "monochrome": [(0, 0, 0), (60, 60, 60), (140, 140, 140), (200, 200, 200)],
}

cfg = plugin_config("domain_warp", {
    "scheme": "ocean",  # one of PRESETS
    "strength": 12,  # how far a nudge can push, in table cells
    "speed": 2,  # 1 slow, 2 medium, 4 fast
    "scale": 3.1,  # bigger means smaller swirls
})
scheme = cfg["scheme"]
strength = cfg["strength"]
speed = cfg["speed"]
scale = cfg["scale"]

STOPS = PRESETS.get(scheme, PRESETS["ocean"])

# packed like the screen stores a pixel: 0xaabbggrr
PALETTE = array("I", [0] * 256)
for i in range(256):
    pos = i * 3 / 255
    k = min(int(pos), 2)
    f = pos - k
    lo = STOPS[k]
    hi = STOPS[k + 1]
    r = int(lo[0] + (hi[0] - lo[0]) * f)
    g = int(lo[1] + (hi[1] - lo[1]) * f)
    b = int(lo[2] + (hi[2] - lo[2]) * f)
    PALETTE[i] = 0xff000000 | (b << 16) | (g << 8) | r

CLOUD = bytearray(WIDTH * HEIGHT)
BHILL = [randrange(256) for _ in range(64)]
# viper takes four args max, so these ride together: time, push, read spacing (x256)
PARAMS = array("i", [0, strength * 2, int(256 * scale / 8)])

def blend(posts, spacing, x, y):
    cx = x // spacing
    cy = y // spacing
    n = 64 // spacing

    tl = posts[cx + cy * n]
    tr = posts[((cx + 1) % n) + cy * n]
    bl = posts[cx + ((cy + 1) % n) * n]
    br = posts[((cx + 1) % n) + ((cy + 1) % n) * n]

    fx = (x % spacing) / spacing
    fy = (y % spacing) / spacing
    # ease in and out at each post so no creases show
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)

    top = tl + (tr - tl) * fx
    bottom = bl + (br - bl) * fx

    return top + (bottom - top) * fy

# make some noooooooise
for y in range(HEIGHT):
    for x in range(WIDTH):
        CLOUD[x + y * WIDTH] = int(blend(BHILL, 8, x, y))

# stretch to fill 0-255
lo = min(CLOUD)
hi = max(CLOUD)
for i in range(len(CLOUD)):
    CLOUD[i] = (CLOUD[i] - lo) * 255 // (hi - lo)


# every CLOUD read is blend() again, positions x256 (>> 8 cell, & 255 how far in).
# written out five times since a call costs more than the read
@micropython.viper
def warp(cloud: ptr8, pixels: ptr32, pal: ptr32, params: ptr32):  # noqa: F821
    drift = int(params[0])
    push = int(params[1])
    zoom = int(params[2])
    for y in range(64):
        spot_y = y * zoom
        for x in range(64):
            spot_x = x * zoom

            read_x = spot_x + drift
            read_y = spot_y
            cell_x = (read_x >> 8) & 63
            cell_y = (read_y >> 8) & 63
            into_x = read_x & 255
            into_y = read_y & 255
            next_x = (cell_x + 1) & 63
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            top_left = int(cloud[cell_x + row])
            top_right = int(cloud[next_x + row])
            bottom_left = int(cloud[cell_x + next_row])
            bottom_right = int(cloud[next_x + next_row])
            top = top_left + (((top_right - top_left) * into_x) >> 8)
            bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
            height = top + (((bottom - top) * into_y) >> 8)
            sideways = (height - 128) * push
            read_x = spot_x + 8192
            read_y = spot_y + 8192 + drift
            cell_x = (read_x >> 8) & 63
            cell_y = (read_y >> 8) & 63
            into_x = read_x & 255
            into_y = read_y & 255
            next_x = (cell_x + 1) & 63
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            top_left = int(cloud[cell_x + row])
            top_right = int(cloud[next_x + row])
            bottom_left = int(cloud[cell_x + next_row])
            bottom_right = int(cloud[next_x + next_row])
            top = top_left + (((top_right - top_left) * into_x) >> 8)
            bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
            height = top + (((bottom - top) * into_y) >> 8)
            updown = (height - 128) * push

            # second nudge, from where the first landed
            landed_x = spot_x + sideways
            landed_y = spot_y + updown
            read_x = landed_x + 4352 - drift
            read_y = landed_y + 10496
            cell_x = (read_x >> 8) & 63
            cell_y = (read_y >> 8) & 63
            into_x = read_x & 255
            into_y = read_y & 255
            next_x = (cell_x + 1) & 63
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            top_left = int(cloud[cell_x + row])
            top_right = int(cloud[next_x + row])
            bottom_left = int(cloud[cell_x + next_row])
            bottom_right = int(cloud[next_x + next_row])
            top = top_left + (((top_right - top_left) * into_x) >> 8)
            bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
            height = top + (((bottom - top) * into_y) >> 8)
            sideways = (height - 128) * push
            read_x = landed_x + 11520
            read_y = landed_y + 2304 + drift
            cell_x = (read_x >> 8) & 63
            cell_y = (read_y >> 8) & 63
            into_x = read_x & 255
            into_y = read_y & 255
            next_x = (cell_x + 1) & 63
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            top_left = int(cloud[cell_x + row])
            top_right = int(cloud[next_x + row])
            bottom_left = int(cloud[cell_x + next_row])
            bottom_right = int(cloud[next_x + next_row])
            top = top_left + (((top_right - top_left) * into_x) >> 8)
            bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
            height = top + (((bottom - top) * into_y) >> 8)
            updown = (height - 128) * push

            # colour it into a 2x2 block
            read_x = spot_x + sideways
            read_y = spot_y + updown
            cell_x = (read_x >> 8) & 63
            cell_y = (read_y >> 8) & 63
            into_x = read_x & 255
            into_y = read_y & 255
            next_x = (cell_x + 1) & 63
            row = cell_y << 6
            next_row = ((cell_y + 1) & 63) << 6
            top_left = int(cloud[cell_x + row])
            top_right = int(cloud[next_x + row])
            bottom_left = int(cloud[cell_x + next_row])
            bottom_right = int(cloud[next_x + next_row])
            top = top_left + (((top_right - top_left) * into_x) >> 8)
            bottom = bottom_left + (((bottom_right - bottom_left) * into_x) >> 8)
            height = top + (((bottom - top) * into_y) >> 8)
            colour = pal[height]
            i = (x << 1) + (y << 8)
            pixels[i] = colour
            pixels[i + 1] = colour
            pixels[i + 128] = colour
            pixels[i + 129] = colour


def update():
    # speed 2 is ~1.2 cells a second, whatever the frame rate
    PARAMS[0] = time.ticks_ms() * speed * 154 // 1000
    warp(CLOUD, memoryview(screen), PALETTE, PARAMS)
