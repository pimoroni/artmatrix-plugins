import math
import random
import time

from plugin_config import plugin_config

# Settings
cfg = plugin_config("solar_system", {
    "num_planets": 5,  # Number of planets in the system.
    "min_planet_size": 0.2,  # Minimum and maximum planet radius, naturally. The sun has a radius of 1.
    "max_planet_size": 0.4,
    "max_radius": 7.0,  # Maximum radius of the solar system. The view will always be zoomed out to fit, and this will also affect perspective - higher values mean more exaggerated perspective i.e. a wider angle lens. 5-10 gives a good naturalistic look.
    "max_mins_per_orbit": 10.0,  # Designed for very slow orbits but there's no reason they couldn't be fast if you wanted. Not exact, but I timed a 4 minute orbit at 4:03 so they're close enough for the right feel.
    "min_mins_per_orbit": 4.0,
    "max_mins_per_rotation": 4.0,  # As above, but for the spin of the planets themselves.
    "min_mins_per_rotation": 1.0,
    "background": 0,  # 1 to 5, or 0 for random
    "sun_colour": (255, 220, 0),
    "fps_limit": 30,
    "show_fps": False,
})
num_planets = cfg["num_planets"]
min_planet_size = cfg["min_planet_size"]
max_planet_size = cfg["max_planet_size"]
max_radius = cfg["max_radius"]
max_mins_per_orbit = cfg["max_mins_per_orbit"]
min_mins_per_orbit = cfg["min_mins_per_orbit"]
max_mins_per_rotation = cfg["max_mins_per_rotation"]
min_mins_per_rotation = cfg["min_mins_per_rotation"]
background = cfg["background"]
sun_colour = cfg["sun_colour"]
fps_limit = cfg["fps_limit"]
show_fps = cfg["show_fps"]


viewing_distance = max_radius + 1
max_orbital_radians_per_frame = (((1 / max_mins_per_orbit) / 60) / fps_limit) * 2 * math.pi
min_orbital_radians_per_frame = (((1 / min_mins_per_orbit) / 60) / fps_limit) * 2 * math.pi
max_rotational_radians_per_frame = (((1 / max_mins_per_rotation) / 60) / fps_limit) * 2 * math.pi
min_rotational_radians_per_frame = (((1 / min_mins_per_rotation) / 60) / fps_limit) * 2 * math.pi

if background == 0:
    background = random.randint(1, 5)
background_img = image.load(f"/lib/plugins/solar_system/assets/space{background}.png")
tilemap = image.load("/lib/plugins/solar_system/assets/planet.png")
tilemap = tilemap.spritesheet(16, 4)

screen.pen = color.rgb(0, 0, 0)
screen.antialias = image.X4
screen.font = rom_font.sins

W, H = screen.width, screen.height
CX, CY = W / 2, H / 2
ASPECT_RATIO = W / H


def vector_lerp(a, b, t):
    x = a.x + ((b.x - a.x) * t)
    y = a.y + ((b.y - a.y) * t)
    return vec2(x, y)


class Planet:
    def __init__(self, o_radius, o_angle, o_speed, radius, r_angle, r_speed, sun=False):
        self.orbital_radius = o_radius
        self.orbital_angle = o_angle
        self.orbital_speed = o_speed
        self.x = 0
        self.y = 0
        self.radius = radius
        self.colour = color.rgb(random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))
        self.sun = sun
        self.rotation_angle = r_angle
        self.rotation_speed = r_speed

    def update(self):
        self.x = self.orbital_radius * math.cos(self.orbital_angle)
        self.y = self.orbital_radius * math.sin(self.orbital_angle) + viewing_distance
        self.inner_x = (self.orbital_radius - self.radius) * math.cos(self.orbital_angle)
        self.inner_y = (self.orbital_radius - self.radius) * math.sin(self.orbital_angle) + viewing_distance
        self.outer_x = (self.orbital_radius + self.radius) * math.cos(self.orbital_angle)
        self.outer_y = (self.orbital_radius + self.radius) * math.sin(self.orbital_angle) + viewing_distance
        self.orbital_angle += self.orbital_speed
        self.orbital_angle %= math.pi * 2
        self.rotation_angle += self.rotation_speed
        self.rotation_angle %= math.pi * 2

    def draw(self):
        coords = perspective_transform(self.x, self.y)
        drawing_radius = 200 * (self.radius / self.y)
        planet = shape.circle(coords, drawing_radius)

        if self.sun:
            stops = [(0, color.rgb(255, 255, 255, 255)), (0.6, color.rgb(255, 255, 255, 255)), (0.7, color.rgb(*sun_colour)), (1, color.rgb(255, 255, 255, 0))]
            screen.pen = brush.gradient(brush.RADIAL, centre_point.x, centre_point.y, centre_point.x, centre_point.y + drawing_radius, stops)
            screen.shape(planet)
        else:
            transform = mat3().translate(coords.x + drawing_radius, coords.y + drawing_radius).scale((1 / 64) * (2 * drawing_radius))
            frame = 64 - int((self.rotation_angle / (2 * math.pi)) * 64)

            frame_x = frame % 16
            frame_y = frame // 16
            screen.pen = brush.image(tilemap.sprite(frame_x, frame_y), transform)
            screen.shape(planet)

            screen.alpha = 128
            screen.pen = self.colour
            screen.shape(planet)
            screen.alpha = 255

            t = (self.orbital_angle / (2 * math.pi)) * 2
            if t > 1:
                t = 2 - t
            t = 1 - abs((t * 2) - 1)

            sin_t = math.sin(self.orbital_angle)
            penumbra_width = drawing_radius * 0.5

            inner = perspective_transform(self.inner_x, self.inner_y)
            outer = perspective_transform(self.outer_x, self.outer_y)
            screen_dir = (coords - centre_point).normalized()

            if self.y >= viewing_distance:
                gradient_centre = vector_lerp(centre_point, inner, sin_t)
                gradient_outer = vector_lerp(coords, inner + (screen_dir * drawing_radius), sin_t)
                gradient_radius = (gradient_outer - gradient_centre).length()
                gradient_stop_size = penumbra_width / gradient_radius

                stops = [(0, color.rgb(255, 255, 255, 64)), (1 - gradient_stop_size, color.rgb(255, 255, 255, 64)), (1, color.rgb(0, 0, 0, 96))]

            else:
                way_outer = outer + (outer - centre_point)
                gradient_centre = vector_lerp(way_outer, outer, t)
                gradient_outer = vector_lerp(coords - (screen_dir * penumbra_width), outer - (screen_dir * drawing_radius) - (screen_dir * penumbra_width), t)
                gradient_radius = (gradient_outer - gradient_centre).length()
                gradient_stop_size = penumbra_width / gradient_radius

                stops = [(0, color.rgb(0, 0, 0, 96)), (1 - gradient_stop_size, color.rgb(0, 0, 0, 96)), (1, color.rgb(255, 255, 255, 64))]

            screen.pen = brush.gradient(brush.RADIAL, gradient_centre.x, gradient_centre.y, gradient_outer.x, gradient_outer.y, stops)
            screen.shape(planet)


def perspective_transform(x, y):
    dist = 10 / y
    if system.radius > 0:
        screen_x = (((x * CX) / system.radius) * dist) + CX
    else:
        screen_x = CX
    screen_y = (dist * CY * 0.2) + (CY / 2)

    return vec2(screen_x, screen_y)


class System:
    def __init__(self):
        self.planets = []
        self.radius = 0
        self.transform = mat3()

    def add_sun(self):
        o_radius = 0
        o_angle = 0
        o_speed = 0
        radius = 1
        r_angle = 0
        r_speed = 0
        self.planets.append(Planet(o_radius, o_angle, o_speed, radius, r_angle, r_speed, sun=True))

    def add_planet(self):
        o_radius = random.uniform((max_radius / 10) + 2, max_radius)
        radius = random.uniform(min_planet_size, max_planet_size)
        o_angle = random.uniform(1, 2 * math.pi)
        o_speed = random.uniform(min_orbital_radians_per_frame, max_orbital_radians_per_frame)
        radius = random.uniform(0.2, 0.4)
        r_angle = random.uniform(1, 2 * math.pi)
        r_speed = random.uniform(min_rotational_radians_per_frame, max_rotational_radians_per_frame)
        self.planets.append(Planet(o_radius, o_angle, o_speed, radius, r_angle, r_speed))

    def update(self):
        self.planets.sort(key=lambda x: x.y, reverse=True)
        i = 0
        for planet in self.planets:
            if planet.orbital_radius > i:
                i = planet.orbital_radius
        self.radius = i
        self.transform = mat3()


system = System()
system.add_sun()
for _ in range(num_planets):
    system.add_planet()

centre_point = perspective_transform(0, viewing_distance)

last_frame = time.ticks_ms()


def update():
    global last_frame

    now = time.ticks_ms()
    elapsed = now - last_frame
    if elapsed >= 1000 / fps_limit:
        screen.blit(background_img, 0, 0)
        last_frame = now

        if show_fps:
            screen.pen = color.white
            screen.text(str(1000 / elapsed), 0, 0)

        for planet in system.planets:
            planet.update()

        system.update()

        for planet in system.planets:
            planet.draw()
