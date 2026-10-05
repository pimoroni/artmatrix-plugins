import random
import time
import micropython
from micropython import const

from plugin_config import plugin_config

# These need to be constants for the viper optimized block below.
WIDTH = const(128 + 2)
HEIGHT = const(128 + 4)
fire_spawns = const(23)
damping_factor = const(810)  # int(0.98 * (1 << 12) // 5)

heat_array = bytearray(HEIGHT * WIDTH * 4)

screen.font = rom_font.awesome
screen.pen = color.white

# The following value is exposed to the web interface.
cfg = plugin_config("this_is_fine", {
    "message": "this is fine.",  # Message, obvs.
    "scroll": False,  # Whether to scroll the message.
    "pixel_size": 3,  # Resolution of the fire in pixels. Max 3.
})
message = cfg["message"]
scroll = cfg["scroll"]
pixel_size = cfg["pixel_size"]


@micropython.viper
def make_heat() -> ptr32:     # noqa: F821
    return ptr32(heat_array)  # noqa: F821


@micropython.viper
def _update(heat: ptr32):  # noqa: F821
    # clear the bottom row and then add a new fire seed to it
    for x in range(WIDTH):
        heat[x + WIDTH * (HEIGHT - 1)] = 0
        heat[x + WIDTH * (HEIGHT - 2)] = 0

    for _ in range(fire_spawns):
        x = int(random.randint(2, WIDTH - 3))
        heat[x + 0 + WIDTH * (HEIGHT - 1)] += 65536
        heat[x + 1 + WIDTH * (HEIGHT - 1)] += 65536
        heat[x - 1 + WIDTH * (HEIGHT - 1)] += 65536
        heat[x + 0 + WIDTH * (HEIGHT - 2)] += 65536
        heat[x + 1 + WIDTH * (HEIGHT - 2)] += 65536
        heat[x - 1 + WIDTH * (HEIGHT - 2)] += 65536

    # Propagate the fire using fixed point arithmetic
    for y in range(HEIGHT - 2):
        for x in range(1, WIDTH - 1):
            new_heat = heat[x + WIDTH * y] + heat[x + WIDTH * (y + 1)] + heat[x + WIDTH * (y + 2)] + heat[x - 1 + WIDTH * (y + 1)] + heat[x + 1 + WIDTH * (y + 1)]
            new_heat *= damping_factor
            heat[x + WIDTH * y] = new_heat >> 12


@micropython.viper
def draw(heat: ptr32, graphics: ptr32, pixel_size: int):  # noqa: F821
    # Convert the fixed point heat values into RGB888 colours,
    # writing directly to the graphics buffer

    y = 0
    while y < HEIGHT - 4:
        x = 0
        while x < WIDTH - 2:
            value = heat[x + 1 + y * WIDTH]
            if value < 9830:
                colour = 0
            elif value < 16384:
                colour = 0x141414
            elif value < 20000:
                colour = 0x141420
            elif value < 22938:
                colour = 0x001eb4
            elif value < 29490:
                colour = 0x00a0dc
            else:
                colour = 0xb4ffff

            graphics[x + (128 * y)] = colour
            if pixel_size > 1:
                graphics[x + (128 * (y + 1))] = colour
                graphics[x + 1 + (128 * y)] = colour
                graphics[x + 1 + (128 * (y + 1))] = colour
            if pixel_size > 2:
                # row -1 and column -1 fall outside the buffer
                if y > 0:
                    graphics[x + (128 * (y - 1))] = colour
                    graphics[x + 1 + (128 * (y - 1))] = colour
                if x > 0:
                    graphics[x - 1 + (128 * y)] = colour
                    graphics[x - 1 + (128 * (y + 1))] = colour
                    if y > 0:
                        graphics[x - 1 + (128 * (y - 1))] = colour

            x += pixel_size
        y += pixel_size


heat = make_heat()
t_total = 0
t_frames = 0

text_window = screen.window(0, 0, screen.width, screen.height / 2)
my_scroll = text.scroll(message, font_face=rom_font.awesome, target=text_window, gap=20)


def update():
    global t_total, t_frames

    t_start = time.ticks_ms()

    _update(heat)
    draw(heat, memoryview(screen), pixel_size)

    screen.pen = color.white
    screen.font = rom_font.ark

    if scroll:
        my_scroll()
    else:
        x, y = screen.measure_text(message)
        screen.text(message, (128 - x) / 2, 25)

    t_end = time.ticks_ms()

    t_total += time.ticks_diff(t_end, t_start)
    t_frames += 1

    if t_frames == 100:
        per_frame_avg = t_total / t_frames
        print(f"100 frames in {t_total}ms, avg {per_frame_avg:.02f}ms per frame, {1000 / per_frame_avg:.02f} FPS")
        t_frames = 0
        t_total = 0
