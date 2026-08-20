from random import getrandbits
import time

CX = int(screen.width / 2)
CY = int(screen.height / 2)
BITS = 8
BLACK = color.rgb(0, 0, 0)

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

        Star.Stars.append(self)

    def step(self):
        self.z -= 1
        if self.z < abs(self.x) or self.z < abs(self.y):
            self.x = getrandbits(BITS) - CX + 0.0001
            self.y = getrandbits(BITS) - CY + 0.0001
            self.z = CX

        self.px = self.x
        self.py = self.y

        self.x = self.x / self.z * CX
        self.y = self.y / self.z * CY

        self.size = (CX - self.z) / 8

    def draw(self):
        screen.pen = color.white
        screen.circle(self.x + CX, self.y + CY, self.size)
        screen.pen = color.blue
        screen.line(self.x + CX, self.y + CY, self.px + CX, self.py + CY)

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
                star.draw()


for _ in range(60):
    Star()


def update():
    Star.update()
