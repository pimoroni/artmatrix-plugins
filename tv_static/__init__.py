from random import getrandbits, randint
import time

from plugin_config import plugin_config

cfg = plugin_config("tv_static", {
    "size": 4,
    "flicker": "medium",
})
size = cfg["size"]
flicker = cfg["flicker"]
grid = 128 // size
blocks_per_frame = int(grid * grid * {"low": 0.05, "medium": 0.1, "high": 0.2}.get(flicker, 0.1))


FRAME_TARGET = 33.3
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

        screen.pen = brush.glitch(20)
        screen.rectangle(0, 0, screen.width, screen.height)

        screen.pen = brush.crt(3, 40)
        screen.rectangle(0, 0, screen.width, screen.height)
