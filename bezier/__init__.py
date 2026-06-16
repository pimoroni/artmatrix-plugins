import random
import sys
import os
import time

sys.path.insert(0, "/bezier")
os.chdir("/bezier")

screen.antialias = image.X4
screen.font = rom_font.sins

# These values are exposed to the web interface.
curves = 1  # Number of separate loops to display, minimum 1
points = 5  # Number of control points each loop is made up of, minimum 2
num_segs = 10  # Number of line segments in each cureve, minimum 1
trail_length = 3  # Length of ghostly trail left, 0 = no trail, 5 = no fade
max_speed = 1  # Points will move at random speeds between this value and half of this value.
thickness = 2  # Line thickness - note line will become less smooth as thickness goes up.
colour = (0, 0, 0)  # Colour of the loop(s). If set to 0, 0, 0 the loops will be rainbow coloured.
show_fps = False  # Displays framerate in the top left corner of the screen.


class BezierPoint:
    def __init__(self, rect):
        self.x = random.randint(int(rect.x), int(rect.r))
        self.y = random.randint(int(rect.y), int(rect.b))
        self.rect = rect
        self.vx = random.uniform(max_speed / 2, max_speed)
        self.vy = random.uniform(max_speed / 2, max_speed)

    @property
    def pos(self):
        return vec2(self.x, self.y)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.x = clamp(self.x, self.rect.x, self.rect.r)
        self.y = clamp(self.y, self.rect.y, self.rect.b)
        if self.x <= self.rect.x or self.x >= self.rect.r:
            new_vx = random.uniform(max_speed / 2, max_speed)
            if self.vx > 0:
                new_vx = -new_vx
            self.vx = new_vx
        if self.y <= self.rect.y or self.y >= self.rect.b:
            new_vy = random.uniform(max_speed / 2, max_speed)
            if self.vy > 0:
                new_vy = -new_vy
            self.vy = new_vy

    def draw(self):
        screen.circle(self.x, self.y, 3)


class BezierLoop:
    def __init__(self, colour):
        self.points = []
        for _i in range(points):
            self.points.append(BezierPoint(rect(0, 0, 128, 128)))
        self.intersects = []
        self.colour = colour
        self.segments = []

    def calc_handles(self):
        smoothness = 0.4
        n = len(self.points)
        self.intersects = []
        for i in range(n):
            p_prev = self.points[(i - 1) % n]
            p_curr = self.points[i]
            p_next = self.points[(i + 1) % n]

            v = p_next.pos - p_prev.pos

            h1 = p_curr.pos - v * smoothness
            h2 = p_curr.pos + v * smoothness
            self.intersects.append((h1, h2))

    def update(self):
        for point in self.points:
            point.update()

        self.calc_handles()

    def draw_line(self):
        self.segments.clear()

        for q in range(len(self.points)):
            p0 = self.points[q].pos
            p3 = self.points[(q + 1) % len(self.points)].pos
            p1 = self.intersects[q][1]
            p2 = self.intersects[(q + 1) % len(self.intersects)][0]
            for i in range(num_segs):
                j = i / num_segs
                primary0 = lerp(p0, p1, j)
                primary1 = lerp(p1, p2, j)
                primary2 = lerp(p2, p3, j)
                secondary1 = lerp(primary0, primary1, j)
                secondary2 = lerp(primary1, primary2, j)
                tertiary = lerp(secondary1, secondary2, j)
                self.segments.append(tertiary)

        screen.pen = color.rgb(self.colour[0], self.colour[1], self.colour[2])
        for i in range(len(self.segments)):
            if self.colour[0] + self.colour[1] + self.colour[2] == 0:
                hue = (1 / len(self.segments)) * i * 255
                screen.pen = color.hsv(hue, 255, 255)
            seg = shape.line(self.segments[i].x, self.segments[i].y, self.segments[(i + 1) % len(self.segments)].x, self.segments[(i + 1) % len(self.segments)].y, thickness)
            screen.shape(seg)

    def draw_points(self):
        for i in range(len(self.segments)):
            if i % self.num_segs == 0:
                screen.pen = color.white
                screen.circle(self.segments[i], 2)


def lerp(pointa, pointb, t):
    x = pointa.x + t * (pointb.x - pointa.x)
    y = pointa.y + t * (pointb.y - pointa.y)
    return vec2(x, y)


def clamp(value, minval, maxval):
    return max(min(value, maxval), minval)


trail_length_val = max(min((40 - (8 * trail_length)), 40), 0)
if trail_length == 0:
    trail_length_val = 255
clear_colour = color.rgb(0, 0, 0, trail_length_val)

loops = []
for _i in range(curves):
    loops.append(BezierLoop(colour))

screen.pen = color.rgb(0, 0, 0)
screen.clear()

last_ticks = time.ticks_ms()

while True:

    screen.pen = clear_colour
    screen.clear()

    for loop in loops:
        loop.update()
        loop.draw_line()
        # loop.draw_points()

    if show_fps:
        now = time.ticks_ms()
        frametime = now - last_ticks
        last_ticks = now
        fps = 1000 / frametime

        screen.pen = color.rgb(0, 0, 0)
        screen.rectangle(0, 0, 45, 12)

        screen.font = rom_font.sins
        screen.pen = color.red
        screen.text(str(fps), 0, 0)

    display.update()
