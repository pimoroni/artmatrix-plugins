from math import atan2, degrees, sqrt
from random import getrandbits
import time

from plugin_config import plugin_config

CX = int(screen.width / 2)
CY = int(screen.height / 2)
BITS = 8
BLACK = color.rgb(0, 0, 0)

# These values are exposed to the web interface.
cfg = plugin_config("stars", {
    "speed": 1.0,  # 0.5 slow, 1.0 normal, 2.0 fast
    "stars": 60,  # 30 sparse, 60 normal, 75 dense
    "trail_colour": (89, 125, 206),
})
speed = cfg["speed"]
stars = cfg["stars"]
trail_colour = cfg["trail_colour"]
TRAIL = color.rgb(trail_colour[0], trail_colour[1], trail_colour[2])

FRAME_TARGET = 16
last = None


class Star:

    Stars = []

    def __init__(self):
        self.x = getrandbits(BITS) - CX + 0.0001
        self.y = getrandbits(BITS) - CY + 0.0001
        self.px = self.x
        self.py = self.y
        self.z = CX
        self.size = 0.4
        self.dot = shape.regular_polygon(0, 0, 1, 12)
        self.tail = shape.line(vec2(0, 0), vec2(1, 0), 1)

        Star.Stars.append(self)

    def step(self):
        self.z -= speed
        if self.z < abs(self.x) or self.z < abs(self.y):
            self.x = getrandbits(BITS) - CX + 0.0001
            self.y = getrandbits(BITS) - CY + 0.0001
            self.z = CX

        self.px = self.x
        self.py = self.y

        self.x = self.x / self.z * CX
        self.y = self.y / self.z * CY

        self.size = (CX - self.z) / 8

        dx = self.px - self.x
        dy = self.py - self.y
        size = self.size or 0.001
        m = mat3.trs(self.x + CX, self.y + CY, degrees(atan2(dy, dx)), size)
        self.dot.transform = m
        self.tail.transform = m.scale(sqrt(dx * dx + dy * dy) / size, 1 / size)

    @staticmethod
    def update():
        global last
        if last is None or time.ticks_diff(time.ticks_ms(), last) >= FRAME_TARGET:
            last = time.ticks_ms()

            screen.pen = BLACK
            screen.clear()
            sl = Star.Stars
            for star in sl:
                star.step()
            screen.pen = TRAIL
            for star in sl:
                screen.shape(star.tail)
            screen.pen = color.white
            for star in sl:
                screen.shape(star.dot)


for _ in range(stars):
    Star()


def update():
    Star.update()
