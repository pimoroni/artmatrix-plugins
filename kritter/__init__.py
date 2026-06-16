import math
import random
import time
from ulab import numpy as np
import sys
import os

sys.path.insert(0, "/kritter")
os.chdir("/kritter")

import blob
import draw_planet

bg = image.load("assets/space.png")

colours = [color.rgb(255, 0, 0),
           color.rgb(255, 255, 0),
           color.rgb(0, 255, 0),
           color.rgb(255, 0, 255),
           color.rgb(0, 0, 255)]

rock_colours = [(112, 103, 93),
                (145, 132, 115),
                (181, 213, 228),
                (83, 123, 136),
                (170, 177, 183),
                (199, 168, 126),
                (181, 138, 94),
                (122, 81, 52)]

screen.antialias = image.X4

# These values are exposed to the web interface
num_kritters = 5  # The number of kritters jumping around.
num_planets = 10  # The number of planets to jump around on.
num_targets = 10  # The number of invisible jump targets to trigger the kritter's jumps. Higher values means more jumping.
jump_chaos = 30  # The max random variation from vertical, in degrees, on any given jump.
gravity_strength = 5  # The strength of the planets' gravitational fields.
planet_radius_min = 5  # Minimum radius in pixels for each planet.
planet_radius_max = 12  # Maximum radius in pixels for each planet.
planet_speed_min = 0.05  # Minimum scrolling speed for planets.
planet_speed_max = 0.2  # Maximum scrolling speed for planets.
planet_rotation_speed_min = 0.5  # Minimum rotation speed for planets in degrees per frame.
planet_rotation_speed_max = 1.5  # Maximum rotation speed for planets in degrees per frame.
show_fps = False  # Displays framerate in the top left corner of the screen.


class Planet:
    def __init__(self, pos=None):
        self.radius = random.randint(planet_radius_min, planet_radius_max)
        if pos is None:
            self.pos = vec2(128 + self.radius, random.randint(20, 108))
        else:
            self.pos = pos
        self.mass = (4 / 3) * np.pi * (self.radius ** 3)
        self.speed = random.uniform(planet_speed_min, planet_speed_max)
        self.rotation = 0
        self.rotation_speed = random.uniform(-planet_rotation_speed_min, -planet_rotation_speed_max)
        self.colour = random.choice(rock_colours)
        self.pattern = random.randint(0, 4)

    def calc_gravity(self, pos, mass):
        rel_vec = self.pos - pos
        d_squared = (rel_vec.x ** 2) + (rel_vec.y ** 2)
        d = math.sqrt(d_squared)
        force = gravity_strength * 0.000001 * ((self.mass * mass) / d_squared)
        normal_vec = rel_vec / d
        return normal_vec * force

    def move(self):
        self.pos.x -= self.speed
        self.rotation += self.rotation_speed
        self.rotation %= 360

    def draw(self):
        draw_planet.draw_planet(self)


class Kritter:
    def __init__(self, pos, radius, colour):
        self.pos = pos
        self.radius = radius
        self.mass = (4 / 3) * np.pi * (self.radius ** 3)
        self.velocity = vec2(0, 0)
        self.acceleration = vec2(0, 0)
        self.grounded = False
        self.ground_normal = vec2(0, 0)
        self.ground_planet = None
        self.colour = colours[colour]
        self.anim_offset = random.randint(0, 360)

    @property
    def speed(self):
        return math.sqrt(self.velocity.x ** 2 + self.velocity.y ** 2)

    @property
    def direction(self):
        return self.velocity / self.speed

    def reset(self):
        self.acceleration = vec2(0, 0)

    def process_gravity(self):
        if not self.grounded:
            for planet in planets:
                self.acceleration += planet.calc_gravity(self.pos, self.mass)

    def orbit(self, planet):
        rotation = math.radians(planet.rotation_speed)
        cos = math.cos(rotation)
        sin = math.sin(rotation)
        new_x = (self.pos.x * cos) - (self.pos.y * sin)
        new_y = (self.pos.x * sin) + (self.pos.y * cos)
        return vec2(new_x, new_y)

    def move(self):
        self.velocity += self.acceleration
        self.pos += self.velocity
        if self.grounded:
            self.pos.x -= self.ground_planet.speed
            self.pos -= self.ground_planet.pos
            self.pos = self.orbit(self.ground_planet)
            self.pos += self.ground_planet.pos
            self.ground_normal = direction(self.pos, self.ground_planet.pos)
        self.clamp_bounds()

    def clamp_bounds(self):
        if self.pos.x < -50 and self.velocity.x < 0:
            self.velocity.x = -self.velocity.x
        if self.pos.x > 178 and self.velocity.x > 0:
            self.velocity.x = -self.velocity.x
        if self.pos.y < -50 and self.velocity.y < 0:
            self.velocity.y = -self.velocity.y
        if self.pos.y > 178 and self.velocity.y > 0:
            self.velocity.y = -self.velocity.y

    def process_collision(self, others):
        for other in others:
            pos_vector = self.pos - other.pos

            distance_squared = pos_vector.x ** 2 + pos_vector.y ** 2
            if distance_squared > (self.radius + other.radius) ** 2:
                continue

            distance = math.sqrt(distance_squared)
            overlap = distance - (self.radius + other.radius)

            normal = pos_vector / distance
            tangent = vec2(-normal.y, normal.x)

            self.pos -= normal * overlap

            self.grounded = True
            self.ground_normal = normal
            self.ground_planet = other

            if self.grounded:
                self.velocity = vec2(0, 0)
            else:
                projection = tangent * ((self.velocity.x * tangent.x) + (self.velocity.y * tangent.y))
                new_vector = (projection * 2) - self.velocity
                self.velocity = new_vector * 0.9

    def look_for_dust(self):
        for dust in spacedust:
            pos_vector = dust.pos - self.pos

            distance_squared = pos_vector.x ** 2 + pos_vector.y ** 2
            if distance_squared < self.radius ** 2:
                dust.reset()
            elif self.grounded:
                distance = math.sqrt(distance_squared)
                dot_product = (self.ground_normal.x * pos_vector.x) + (self.ground_normal.y * pos_vector.y)
                arccos = min(1, max(-1, dot_product / distance))
                angle = math.acos(arccos)
                if abs(math.degrees(angle)) < 3 and distance < 72 and not random.randint(0, 2):
                    self.jump()

    def jump(self):
        self.grounded = False
        jump_angle = math.radians(random.randint(-jump_chaos, jump_chaos))
        cos = math.cos(jump_angle)
        sin = math.sin(jump_angle)
        new_x = (self.ground_normal.x * cos) - (self.ground_normal.y * sin)
        new_y = (self.ground_normal.x * sin) + (self.ground_normal.y * cos)
        jump_force = vec2(new_x, new_y) * (self.ground_planet.radius / 10)
        self.acceleration += jump_force

    def draw(self):
        screen.pen = color.white
        if self.grounded:
            angle = math.degrees(math.atan2(self.ground_normal.x, -self.ground_normal.y))
            blob.draw_blob(self.pos, angle, self.colour, self.anim_offset)
        else:
            angle = math.degrees(math.atan2(-self.acceleration.x, self.acceleration.y))
            blob.draw_blob_flying(self.pos, angle, self.acceleration, self.colour, self.anim_offset)


class Spacedust:
    def __init__(self):
        self.colour = random.choice(colours)
        x = random.randint(0, 128)
        y = random.randint(0, 128)
        self.pos = vec2(x, y)
        vx = random.uniform(-0.5, 0.5)
        vy = random.uniform(-0.5, 0.5)
        self.velocity = vec2(vx, vy)

    def reset(self):
        self.colour = random.choice(colours)
        x = random.randint(0, 128)
        y = random.randint(0, 128)
        self.pos = vec2(x, y)
        vx = random.uniform(-0.5, 0.5)
        vy = random.uniform(-0.5, 0.5)
        self.velocity = vec2(vx, vy)

    def move(self):
        new_pos = self.pos + self.velocity
        if new_pos.x < 0 or new_pos.x > 128:
            self.velocity.x *= -1
        if new_pos.y < 0 or new_pos.y > 128:
            self.velocity.y *= -1
        self.pos += self.velocity

    def draw(self):
        me = shape.circle(self.pos.x, self.pos.y, 2)
        screen.pen = self.colour
        screen.shape(me)


def direction(start, destination):
    pos_vector = start - destination
    distance = math.sqrt(pos_vector.x ** 2 + pos_vector.y ** 2)
    return pos_vector / distance


def add_planet():
    planets.append(Planet())


planets = []
for _i in range(num_planets):
    planets.append(Planet(vec2(random.randint(20, 108), random.randint(20, 108))))

kritters = []
for i in range(num_kritters):
    j = i % len(colours)
    kritters.append(Kritter(vec2(random.randint(0, 128), random.randint(0, 128)), 5, j))

spacedust = []

for _i in range(num_targets):
    spacedust.append(Spacedust())

last_ticks = time.ticks_ms()

while True:
    screen.blit(bg, vec2(0, 0))

    for kritter in kritters:
        kritter.reset()
        kritter.process_gravity()
        kritter.process_collision(planets)
        kritter.look_for_dust()
        kritter.move()
        kritter.draw()

    for planet in planets:
        planet.move()
        planet.draw()

    for planet in reversed(planets):
        if planet.pos.x <= -planet.radius:
            for kritter in kritters:
                if kritter.grounded and kritter.ground_planet == planet:
                    kritter.grounded = False
            planets.remove(planet)
            add_planet()

    for dust in spacedust:
        dust.move()

    if show_fps:
        now = time.ticks_ms()
        frametime = now - last_ticks
        last_ticks = now
        fps = 1000 / frametime

        screen.font = rom_font.sins
        screen.pen = color.red
        screen.text(str(fps), 0, 0)

    display.update()
