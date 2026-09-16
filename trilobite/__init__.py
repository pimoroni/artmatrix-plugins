import random
import math
import time
from plugin_config import plugin_config

width = 128
height = 128

screen.font = rom_font.sins

trilo_sprite = image.load("/lib/plugins/trilobite/assets/trilobite.png")
ammo_sprite = image.load("/lib/plugins/trilobite/assets/ammonite.png")
track_sprite = SpriteSheet("/lib/plugins/trilobite/assets/track.png", 5, 1)
sand = image(128, 128)
sand_light = color.rgb(252, 248, 177)
sand.pen = sand_light
sand.clear()

# These values are exposed in the web interface.
cfg = plugin_config("trilobite", {
    "num_trilobites": 1,
    "trilobite_speed_max": 0.4,
    "trilobite_speed_min": 0.2,
    "show_fps": False,
})
num_trilobites = cfg["num_trilobites"]
trilobite_speed_max = cfg["trilobite_speed_max"]
trilobite_speed_min = cfg["trilobite_speed_min"]
show_fps = cfg["show_fps"]


class Ammonite:
    def __init__(self, speed):
        self.x = random.randint(0, width)
        self.y = random.randint(0, height)
        self.angle = random.randint(0, 360)
        self.dx, self.dy = self.get_vectors()
        self.speed = speed

    def get_vectors(self):
        x = math.cos(math.radians(self.angle))
        y = math.sin(math.radians(self.angle))
        return x, y

    def update(self):
        self.x += self.dx * self.speed
        self.y += self.dy * self.speed
        if self.x < 0 or self.x > 128:
            self.dx = -self.dx
        if self.y < 0 or self.y > 128:
            self.dy = -self.dy

    def draw(self):
        screen.blit(ammo_sprite, vec2(self.x - 4, self.y - 4))


class Trilobite:
    def __init__(self):
        self.x = random.randint(0, 128)
        self.y = random.randint(0, 128)
        self.speed = random.uniform(trilobite_speed_max, trilobite_speed_min)
        self.angle = random.randint(0, 360)
        self.randomise_target()
        self.track = track_sprite.sprite(0, 0)

    def get_vectors(self):
        x = math.cos(math.radians(self.angle))
        y = math.sin(math.radians(self.angle))
        return x, y

    def randomise_target(self):
        self.target = Ammonite(self.speed / 2)

    def get_target_angle(self, dx, dy):
        rel_pos = vec2(self.target.x - self.x, self.target.y - self.y)
        dot_product = (rel_pos.x * dx) + (rel_pos.y * dy)
        cross_product = (rel_pos.y * dx) - (rel_pos.x * dy)
        view_angle = math.atan2(cross_product, dot_product)
        dist = math.sqrt(rel_pos.x ** 2 + rel_pos.y ** 2)
        return view_angle, dist

    def update(self):
        self.target.update()
        dx, dy = self.get_vectors()
        self.x += dx * self.speed
        self.y += dy * self.speed
        view_angle, dist = self.get_target_angle(dx, dy)
        self.angle += view_angle
        self.angle %= 360
        if dist < 2:
            self.randomise_target()

    def leave_track(self):
        self.track = track_sprite.sprite(random.randint(0, 4), 0)
        transform = mat3().translate(self.x, self.y).rotate(self.angle + 90).translate(-16, -16)
        sand.pen = brush.image(self.track, transform)
        sand.circle(self.x, self.y, 12)

    def draw(self):
        self.leave_track()
        self.target.draw()
        transform = mat3().translate(self.x, self.y).rotate(self.angle + 90).translate(-12, -12)
        screen.pen = brush.image(trilo_sprite, transform)
        trilo_body = shape.rectangle(0, 0, 24, 24)
        trilo_body.transform = transform
        screen.shape(trilo_body)


trilobites = []

for _i in range(num_trilobites):
    trilobites.append(Trilobite())

last_ticks = time.ticks_ms()


def update():
    global last_ticks

    screen.blit(sand, vec2(0, 0))

    for trilobite in trilobites:
        trilobite.update()
        trilobite.draw()

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
