import math
import random
import time


from daylightsaving import DaylightSavingPolicy, DaylightSaving
from plugin_config import plugin_config

GRAVITY_STRENGTH = 5
seconds_gravity_vec = vec2(0, 0)
minutes_gravity_vec = vec2(0, 0)
hours_gravity_vec = vec2(0, 0)

shadow = color.rgb(0, 0, 0, 128)
screen.antialias = image.X4
screen.font = rom_font.sins

# These values are exposed to the web interface
cfg = plugin_config("gravity_clock_vaporwave", {
    "region": "eu",
    "tz_offset": 0,
    "hours_colour": (255, 97, 198),  # The colour for the hour balls and ray. NOTE this is a tuple not a color.rgb so the value survives the round trip to the web interface.
    "minutes_colour": (255, 193, 0),  # The colour for the minute balls and ray. NOTE this is a tuple not a color.rgb so the value survives the round trip to the web interface.
    "seconds_colour": (92, 236, 255),  # The colour for the second balls and ray. NOTE this is a tuple not a color.rgb so the value survives the round trip to the web interface.
    "border_colour": (255, 255, 255),  # The colour of the border. NOTE this is a tuple not a color.rgb so the value survives the round trip to the web interface.
    "line_thickness": 2,  # Thickness to draw the linework.
    "num_balls_hour": 1,  # The number of hour balls to display.
    "num_balls_minute": 5,  # The number of minute balls to display.
    "num_balls_second": 10,  # The number of second balls to display.
    "max_hour_size": 800,  # Maximum size for the hour balls.
    "min_hour_size": 800,  # Minimum size for the hour balls.
    "max_minute_size": 700,  # Maximum size for the minute balls.
    "min_minute_size": 500,  # Minimum size for the minute balls.
    "max_second_size": 470,  # Maximum size for the second balls.
    "min_second_size": 200,  # Minimum size for the second balls.
    "show_fps": False,  # Displays framerate in the top left corner of the screen.
    "show_border": True,  # Displays the squircle border the balls collide with.
    "show_glow": False,  # Displays a neon glow around all screen elements. NOTE this comes with a serious framerate hit.
})
region = cfg["region"]
tz_offset = cfg["tz_offset"]
hours_colour = cfg["hours_colour"]
minutes_colour = cfg["minutes_colour"]
seconds_colour = cfg["seconds_colour"]
border_colour = cfg["border_colour"]
line_thickness = cfg["line_thickness"]
num_balls_hour = cfg["num_balls_hour"]
num_balls_minute = cfg["num_balls_minute"]
num_balls_second = cfg["num_balls_second"]
max_hour_size = cfg["max_hour_size"]
min_hour_size = cfg["min_hour_size"]
max_minute_size = cfg["max_minute_size"]
min_minute_size = cfg["min_minute_size"]
max_second_size = cfg["max_second_size"]
min_second_size = cfg["min_second_size"]
show_fps = cfg["show_fps"]
show_border = cfg["show_border"]
show_glow = cfg["show_glow"]


try:
    with open("/lib/plugins/gravity_clock_vaporwave/config.html", "r", encoding="utf-8") as f:
        config_html = f.read()
except OSError as e:
    print(e)
    config_html = None

# These are the different Daylight Saving time zones, according to the Wikipedia article.
# Timezones are incredibly complex, we've covered the main ones here.
# "zonename": (hemisphere, week, month, weekday, hour, timezone, minutes clocks change by)
# Israel and Palestine each follow different daylight saving rules from standard, and are not included here.
regions = {
    "us": (0, 2, 3, 6, 2, 1, 11, 6, 2, 60),
    "cuba": (0, 2, 3, 6, 0, 1, 11, 6, 1, 60),
    "eu": (0, 0, 3, 6, 1, 0, 10, 6, 1, 60),
    "moldova": (0, 0, 3, 6, 2, 0, 10, 6, 3, 60),
    "lebanon": (0, 0, 3, 6, 0, 0, 10, 6, 0, 60),
    "egypt": (0, 0, 4, 4, 0, 0, 10, 3, 24, 60),
    "chile": (1, 1, 9, 5, 24, 1, 4, 5, 24, 60),
    "australia": (1, 1, 10, 6, 2, 1, 4, 6, 3, 60),
    "nz": (1, 0, 9, 6, 2, 1, 4, 6, 3, 60)
}

region = region if region in regions else "eu"
tz_minutes = tz_offset * 60
hemisphere, week_in, month_in, weekday_in, hour_in, week_out, month_out, weekday_out, hour_out, mins_difference = regions[region]

dstp = DaylightSavingPolicy(hemisphere, week_in, month_in, weekday_in, hour_in,
                            tz_minutes + mins_difference)
stdp = DaylightSavingPolicy(hemisphere, week_out, month_out, weekday_out, hour_out,
                            tz_minutes)

dst = DaylightSaving(dstp, stdp)


# build all the hand shapes, saves rebuilding these every frame. ALL THE FPS.
rw_list = ((30, 60), (40, 40), (50, 20))
shapes_list = {}
for radius, width in rw_list:
    half_width = width / 2

    hand = shape.pie(0, 0, radius, -half_width, half_width)
    hand.stroke(line_thickness)

    outline_a = shape.line(0, 0, 0, -(radius + 3), line_thickness)

    outline_b = shape.pie(0, 0, radius - 10, -half_width, half_width)
    outline_b.stroke(line_thickness)

    outline_c = shape.pie(0, 0, radius - 20, -half_width, half_width)
    outline_c.stroke(line_thickness)

    if radius > 30:
        outline_d = shape.pie(0, 0, radius - 30, -half_width, half_width)
        outline_d.stroke(line_thickness)
    else:
        outline_d = None

    shapes_list[(radius, width)] = (hand, outline_a, outline_b, outline_c, outline_d)


@micropython.native
def on_squircle(pos):
    x = pos.x - 6400
    y = pos.y - 6400
    radius = (x ** 4 + y ** 4) ** 0.25
    new_x = x ** 3
    new_y = y ** 3
    dist = math.sqrt(new_x ** 2 + new_y ** 2)
    tangent = vec2(-new_y, new_x) / -dist
    normal = vec2(new_x, new_y) / -dist
    return radius, tangent, normal


class Clock:
    def __init__(self):
        self.second_rotation = 0
        self.minute_rotation = 0
        self.hour_rotation = 0
        self.last_second = 0
        self.sub_second = 0
        self.last_ms = time.ticks_ms()
        self.last_utc_minute = -1
        self.local_hour = 0
        self.local_minute = 0

    @micropython.native
    def calc_clock(self):
        utc = time.gmtime()
        minute = utc[4]
        second = utc[5]

        if minute != self.last_utc_minute:
            self.last_utc_minute = minute
            local = time.gmtime(dst.localtime(time.mktime(utc)))
            self.local_hour = local[3]
            self.local_minute = local[4]

        if second != self.last_second:
            self.sub_second = 0
            self.last_second = second

        ms = time.ticks_ms()
        self.sub_second += time.ticks_diff(ms, self.last_ms)
        self.last_ms = ms

        self.second_rotation = (second * 6) + (0.006 * self.sub_second)
        self.minute_rotation = (self.local_minute * 6) + (0.1 * second)
        self.hour_rotation = (self.local_hour * 30) + (0.5 * self.local_minute)

    @micropython.native
    def draw_ray(self):
        rotations = (self.hour_rotation, self.minute_rotation, self.second_rotation)
        colours = (hours_colour, minutes_colour, seconds_colour)

        for i in range(3):
            radius, width = rw_list[i]
            hand, outline_a, outline_b, outline_c, outline_d = shapes_list[(radius, width)]

            hand_transform = mat3().translate(64, 64).rotate(rotations[i])
            screen.pen = color.rgb(*colours[i])

            hand.transform = hand_transform
            screen.shape(hand)

            outline_a.transform = hand_transform
            screen.shape(outline_a)

            outline_b.transform = hand_transform
            screen.shape(outline_b)

            outline_c.transform = hand_transform
            screen.shape(outline_c)

            if outline_d is not None:
                outline_d.transform = hand_transform
                screen.shape(outline_d)

    @micropython.native
    def draw_rays(self):
        self.draw_ray()


class Ball:
    def __init__(self, pos, vel, radius, seconds):
        self.radius = radius
        self.pos = pos
        self.velocity = vel
        self.damping = 0.5
        if seconds == 0:
            self.colour = minutes_colour
        elif seconds == 1:
            self.colour = seconds_colour
        elif seconds == 2:
            self.colour = hours_colour
        self.seconds = seconds
        self.mass = math.pi * (self.radius ** 2)

        self.outline = shape.circle(vec2(0, 0), 0.01 * self.radius)
        self.outline.stroke(-line_thickness)

    @property
    @micropython.native
    def speed(self):
        return math.sqrt(self.velocity.x ** 2 + self.velocity.y ** 2)

    @micropython.native
    def move(self):
        self.pos += self.velocity

    @micropython.native
    def draw(self):
        self.outline.transform = mat3().translate(self.pos.x / 100, self.pos.y / 100)
        screen.pen = color.rgb(*self.colour)
        screen.shape(self.outline)

    @micropython.native
    def apply_gravity(self):
        if self.seconds == 0:
            self.velocity += minutes_gravity_vec
        elif self.seconds == 1:
            self.velocity += seconds_gravity_vec
        elif self.seconds == 2:
            self.velocity += hours_gravity_vec

    @micropython.native
    def calc_wall_collisions(self):
        radius, tangent, normal = on_squircle(self.pos)

        if radius + (self.radius) >= 6000:
            direction = self.velocity / self.speed
            dot_product = (direction.x * tangent.x) + (direction.y * tangent.y)
            dist = (radius + self.radius) - 6000
            self.pos += normal * dist
            projection = tangent * ((self.velocity.x * tangent.x) + (self.velocity.y * tangent.y))
            new_vector = (projection * 2) - self.velocity
            damping = abs(dot_product)
            self.velocity = new_vector * damping


@micropython.native
def calc_ball_collisions(ball_a, ball_b):
    pos_vector = ball_a.pos - ball_b.pos

    distance_squared = pos_vector.x ** 2 + pos_vector.y ** 2

    if distance_squared > (ball_a.radius + ball_b.radius) ** 2:
        return

    distance = math.sqrt(distance_squared)

    overlap = distance - ball_a.radius - ball_b.radius

    offset_adjustment = (pos_vector / distance) * (overlap / 2)
    ball_a.pos -= offset_adjustment
    ball_b.pos += offset_adjustment

    vel_a = vec2(ball_a.velocity.x, ball_a.velocity.y)
    vel_b = vec2(ball_b.velocity.x, ball_b.velocity.y)

    total_mass = ball_a.mass + ball_b.mass

    velocity_delta = vel_a - vel_b

    dot_product_a = (velocity_delta.x * pos_vector.x) + (velocity_delta.y * pos_vector.y)
    dot_product_b = (-velocity_delta.x * -pos_vector.x) + (-velocity_delta.y * -pos_vector.y)

    mass_factor_a = (2 * ball_b.mass) / total_mass
    mass_factor_b = (2 * ball_a.mass) / total_mass

    numerator_a = dot_product_a / distance_squared
    numerator_b = dot_product_b / distance_squared

    new_vel_a = pos_vector * numerator_a * mass_factor_a * ball_a.damping
    new_vel_b = (pos_vector * -1) * numerator_b * mass_factor_b * ball_b.damping

    ball_a.velocity -= new_vel_a
    ball_b.velocity -= new_vel_b


@micropython.native
def gravity_vector(direction):
    gravity_rads = direction * 0.01745329252
    gravity_x = math.cos(gravity_rads)
    gravity_y = math.sin(gravity_rads)
    return vec2(gravity_x, gravity_y) * GRAVITY_STRENGTH


border = shape.squircle(64, 64, 60)
border.stroke(line_thickness)

balls = []

if num_balls_second == 1:
    second_increment = 0
else:
    second_increment = (max_second_size - min_second_size) / (num_balls_second - 1)
second_radius = min_second_size
for _i in range(num_balls_second):
    balls.append(Ball(vec2(random.randint(300, 12500), random.randint(300, 12500)), vec2(random.uniform(-1, 1), random.uniform(-1, 1)), second_radius, 1))
    second_radius += second_increment

if num_balls_minute == 1:
    minute_increment = 0
else:
    minute_increment = (max_minute_size - min_minute_size) / (num_balls_minute - 1)
minute_radius = min_minute_size
for _i in range(num_balls_minute):
    balls.append(Ball(vec2(random.randint(300, 12500), random.randint(300, 12500)), vec2(random.uniform(-1, 1), random.uniform(-1, 1)), minute_radius, 0))
    minute_radius += minute_increment

if num_balls_hour == 1:
    hour_increment = 0
else:
    hour_increment = (max_hour_size - min_hour_size) / (num_balls_hour - 1)
hour_radius = min_hour_size
for _i in range(num_balls_hour):
    balls.append(Ball(vec2(random.randint(300, 12500), random.randint(300, 12500)), vec2(random.uniform(-1, 1), random.uniform(-1, 1)), hour_radius, 2))
    hour_radius += hour_increment


ball_combinations = [(balls[i], balls[j]) for i in range(len(balls)) for j in range(i + 1, len(balls))]
last_ticks = time.ticks_ms()
clock = Clock()


def update():
    global seconds_gravity_vec, minutes_gravity_vec, hours_gravity_vec, last_ticks

    screen.pen = color.rgb(0, 0, 0)
    screen.clear()

    clock.calc_clock()
    seconds_gravity_vec = gravity_vector((clock.second_rotation - 90) % 360)
    minutes_gravity_vec = gravity_vector((clock.minute_rotation - 90) % 360)
    hours_gravity_vec = gravity_vector((clock.hour_rotation - 90) % 360)

    for ball in balls:
        ball.move()
        ball.calc_wall_collisions()

    for combination in ball_combinations:
        calc_ball_collisions(combination[0], combination[1])

    for ball in balls:
        ball.apply_gravity()

    if show_glow:
        if show_border:
            screen.pen = color.rgb(*border_colour)
            screen.shape(border)

        for ball in balls:
            ball.draw()
        clock.draw_rays()

        screen.blur(1.5)

    if show_border:
        screen.pen = color.rgb(*border_colour)
        screen.shape(border)

    for ball in balls:
        ball.draw()
    clock.draw_rays()

    if show_fps:
        now = time.ticks_ms()
        frametime = time.ticks_diff(now, last_ticks)
        last_ticks = now
        fps = (1000 / frametime) if frametime != 0 else "999"

        screen.pen = color.rgb(0, 0, 0)
        screen.rectangle(0, 0, 45, 12)

        screen.font = rom_font.sins
        screen.pen = color.red
        screen.text(str(fps), 0, 0)
