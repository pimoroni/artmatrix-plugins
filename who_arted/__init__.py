import time
import random
import math
import sys
import os

sys.path.insert(0, "/lib/plugins/who_arted")
os.chdir("/lib/plugins/who_arted")

eyes_cream = color.rgb(255, 245, 208)
eyes_black = color.rgb(20, 20, 20)
mouth_black = color.rgb(64, 22, 8)

scream = image.load("assets/scream-no-mouth.png")
lisa = image.load("assets/monalisa_noeyes.png")
pearl_base = image.load("assets/pearl_base.png")
pearl_overlay = image.load("assets/pearl_overlay.png")

screen.antialias = image.OFF

eye = shape.circle(0, 0, 2)
mouth_line = shape.line(0, 0, 0, 5, 1)

last_ticks = time.ticks_ms()
changer_last_ticks = time.ticks_ms()
active = False
next_interval = 0
next_duration = 0

# This value is exposed to the web interface.
max_interval = 30  # The maximum time between changes of look direction / expression.
max_duration = 3  # The maximum time to hold Pearl's expression.
piece = 0  # The piece to start on - 0 = lisa, 1 = scream,  2 = pearl
cycle = True  # Whether to stay on the specified piece or cycle through all three.
art_lifetime = 30  # The time in minutes between cycling art.


def update():
    global last_ticks, next_interval, next_duration, active, piece, changer_last_ticks

    now = time.ticks_ms()
    elapsed = now - last_ticks

    if cycle:
        changer_elapsed = now - changer_last_ticks
        if changer_elapsed >= 60000 * art_lifetime:
            piece += 1
            piece %= 3
            changer_last_ticks = now

    if piece == 0:
        screen.pen = mouth_black

        if elapsed >= 1000 * next_interval:
            last_ticks = now
            next_interval = random.randint(1, max_interval)
            active = not active

        screen.blit(lisa, vec2(0, 0))
        screen.rectangle(41 - (2 * active), 39, 3, 3)
        screen.rectangle(57 - (2 * active), 39, 3, 3)

    elif piece == 1:
        screen.blit(scream, vec2(0, 0))

        screen.pen = eyes_cream

        scale_factor = math.cos(now / 100)

        eye.transform = mat3().translate(63, 69).scale(1, 1.2 + (0.1 * scale_factor))
        screen.shape(eye)
        eye.transform = mat3().translate(71, 69).scale(1, 1.2 + (0.1 * scale_factor))
        screen.shape(eye)

        screen.pen = eyes_black

        eye.transform = mat3().translate(62.5, 69).scale(0.3, 0.3)
        screen.shape(eye)
        eye.transform = mat3().translate(70.5, 69).scale(0.3, 0.3)
        screen.shape(eye)

        screen.pen = mouth_black

        for i in range(67, 70):
            j = math.cos(now / 100 + (i - 67) * 1) / 2
            mouth_line.transform = mat3().translate(i, 78 + j)
            screen.shape(mouth_line)

    else:
        if active and elapsed >= 1000 * next_duration:
            last_ticks = now
            next_duration = random.randint(1, max_duration)
            active = False
        elif not active and elapsed >= 1000 * next_interval:
            last_ticks = now
            next_interval = random.randint(1, max_interval)
            active = True

        screen.blit(pearl_base, vec2(0, 0))
        if active:
            screen.blit(pearl_overlay, vec2(0, 0))

    display.update()
