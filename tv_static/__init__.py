from random import getrandbits, randint
import time
import json

grid = 32
size = 4
blocks_per_frame = 100

try:
    with open("/lib/plugins/tv_static/config.json") as f:
        cfg = json.load(f)
        grid = int(cfg["grid"] or 32)
        size = int(cfg["size"] or 4)
        blocks_per_frame = int(cfg["blocks_per_frame"] or 100)
except OSError:
    pass

try:
    with open("/lib/plugins/tv_static/config.html", "r", encoding="utf-8") as f:
        config_html = f.read()
except OSError as e:
    print(e)
    config_html = None


FRAME_TARGET = 16
last = None

# We're using a separate image here so we can make all the changes before it gets blitted to the screen image
# just so it plays nicely with the plugin transition animation
noise_frame = image(screen.width, screen.height)

# Fill the image with squares
for y in range(grid):
    for x in range(grid):
        col = getrandbits(8)
        noise_frame.pen = color.rgb(col, col, col)
        noise_frame.rectangle(x * size, y * size, size, size)


def update():
    global last

    if last is None or time.ticks_diff(time.ticks_ms(), last) >= FRAME_TARGET:
        last = time.ticks_ms()
        # change a smaller number of the squares on screen to give a moving static
        for _ in range(blocks_per_frame):
            x = randint(0, grid)
            y = randint(0, grid)
            col = getrandbits(8)
            noise_frame.pen = color.rgb(col, col, col)
            noise_frame.rectangle(x * size, y * size, size, size)

        # now we blit the frame to the screen image
        screen.blit(noise_frame, 0, 0)
