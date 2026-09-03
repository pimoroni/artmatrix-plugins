import math
import random
import time
import json


from daylightsaving import DaylightSavingPolicy, DaylightSaving
from plugins.gravity_clock_classic import chromeball

GRAVITY_STRENGTH = 5
seconds_gravity_vec = vec2(0, 0)
minutes_gravity_vec = vec2(0, 0)
hours_gravity_vec = vec2(0, 0)

bg = image.load("/lib/plugins/gravity_clock_classic/assets/bg.png")
fg = image.load("/lib/plugins/gravity_clock_classic/assets/fg.png")

shadow = color.rgb(0, 0, 0, 128)
screen.antialias = image.X2
screen.font = rom_font.sins

# These values are exposed to the web interface
region = "eu"
tz_offset = 0
hours_colour = (184, 115, 51)  # The colour for the hour balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
minutes_colour = (171, 171, 70)  # The colour for the minute balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
seconds_colour = (96, 96, 96)  # The colour for the second balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
hour_hand_colour = (184, 115, 51)  # The colour for the hour hand.
minute_hand_colour = (220, 200, 82)  # The colour for the minute hand.
second_hand_colour = (192, 192, 192)  # The colour for the second hand.
num_balls_hour = 1  # The number of hour balls to display.
num_balls_minute = 5  # The number of minute balls to display.
num_balls_second = 10  # The number of second balls to display.
max_hour_size = 800  # Maximum size for the hour balls.
min_hour_size = 800  # Minimum size for the hour balls.
max_minute_size = 700  # Maximum size for the minute balls.
min_minute_size = 500  # Minimum size for the minute balls.
max_second_size = 470  # Maximum size for the second balls.
min_second_size = 200  # Minimum size for the second balls.
show_fps = False  # Displays framerate in the top left corner of the screen.


def hex_to_rgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


try:
    with open("/lib/plugins/gravity_clock_classic/config.json") as f:
        cfg = json.load(f)

        region = cfg["region"] or "eu"
        tz_offset = int(cfg["tz_offset"] or 0)

        hours_colour = hex_to_rgb(cfg["hours_colour"])
        minutes_colour = hex_to_rgb(cfg["minutes_colour"])
        seconds_colour = hex_to_rgb(cfg["seconds_colour"])

        hour_hand_colour = hex_to_rgb(cfg["hour_hand_colour"])
        minute_hand_colour = hex_to_rgb(cfg["minute_hand_colour"])
        second_hand_colour = hex_to_rgb(cfg["second_hand_colour"])

        num_balls_hour = int(cfg["num_balls_hour"] or 1)
        num_balls_minute = int(cfg["num_balls_minute"] or 5)
        num_balls_second = int(cfg["num_balls_second"] or 10)
        max_hour_size = int(cfg["max_hour_size"] or 800)
        min_hour_size = int(cfg["min_hour_size"] or 800)
        max_minute_size = int(cfg["max_minute_size"] or 700)
        min_minute_size = int(cfg["min_minute_size"] or 500)
        max_second_size = int(cfg["max_second_size"] or 470)
        min_second_size = int(cfg["min_second_size"] or 200)
        show_fps = "show_fps" in cfg
except OSError:
    pass


try:
    with open("/lib/plugins/gravity_clock_classic/config.html", "r", encoding="utf-8") as f:
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


second_hand_path = [vec2(0.5, -56),
                    vec2(1.5, -1.3),
                    vec2(2.8, 0),
                    vec2(2.5, 1.3),
                    vec2(1.3, 2.5),
                    vec2(0, 2.8),
                    vec2(-1.3, 2.5),
                    vec2(-2.5, 1.3),
                    vec2(-2.8, 0),
                    vec2(-1.3, -1.5),
                    vec2(-0.5, -56)]

minute_hand_path = [vec2(0, -36),
                    vec2(0.3, -35.7),
                    vec2(0.4, -31.7),
                    vec2(0.6, -27.6),
                    vec2(1.2, -25),
                    vec2(1.7, -23.5),
                    vec2(1.9, -22.2),
                    vec2(1.8, -21.2),
                    vec2(1.4, -20.5),
                    vec2(0.6, -20),
                    vec2(0.8, -2.7),
                    vec2(1.7, -2.2),
                    vec2(2.5, -1.3),
                    vec2(2.8, 0),
                    vec2(2.5, 1.3),
                    vec2(1.3, 2.5),
                    vec2(0, 2.8),
                    vec2(-1.3, 2.5),
                    vec2(-2.5, 1.3),
                    vec2(-2.8, 0),
                    vec2(-1.3, -2.5),
                    vec2(-1.7, -2.2),
                    vec2(-0.8, -2.7),
                    vec2(-0.6, -20),
                    vec2(-1.4, -20.5),
                    vec2(-1.8, -21.2),
                    vec2(-1.9, -22.2),
                    vec2(-1.7, -23.5),
                    vec2(-1.2, -25),
                    vec2(-0.6, -27.6),
                    vec2(-0.4, -31.7),
                    vec2(-0.3, -35.7)]

hour_hand_path = [vec2(0, -26),
                  vec2(0.3, -25.7),
                  vec2(0.4, -21.7),
                  vec2(0.6, -17.6),
                  vec2(1.2, -15),
                  vec2(1.7, -13.5),
                  vec2(1.9, -12.2),
                  vec2(1.8, -11.2),
                  vec2(1.4, -10.5),
                  vec2(0.6, -10),
                  vec2(0.8, -2.7),
                  vec2(1.7, -2.2),
                  vec2(2.5, -1.3),
                  vec2(2.8, 0),
                  vec2(2.5, 1.3),
                  vec2(1.3, 2.5),
                  vec2(0, 2.8),
                  vec2(-1.3, 2.5),
                  vec2(-2.5, 1.3),
                  vec2(-2.8, 0),
                  vec2(-1.3, -2.5),
                  vec2(-1.7, -2.2),
                  vec2(-0.8, -2.7),
                  vec2(-0.6, -10),
                  vec2(-1.4, -10.5),
                  vec2(-1.8, -11.2),
                  vec2(-1.9, -12.2),
                  vec2(-1.7, -13.5),
                  vec2(-1.2, -15),
                  vec2(-0.6, -17.6),
                  vec2(-0.4, -21.7),
                  vec2(-0.3, -25.7)]

minute_hand_shape = shape.custom(minute_hand_path)
second_hand_shape = shape.custom(second_hand_path)
hour_hand = shape.custom(hour_hand_path)

# we don't need the paths anymore, so we can remove them to get the ram back.
del second_hand_path, minute_hand_path, hour_hand_path


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
    def draw_hands(self):
        minute_hand_transform = mat3().translate(64, 64).scale(1.5).rotate(self.minute_rotation)
        minute_hand_transform_shadow = mat3().translate(66, 66).scale(1.5).rotate(self.minute_rotation)

        minute_hand_shape.transform = minute_hand_transform_shadow
        screen.pen = shadow
        screen.shape(minute_hand_shape)

        minute_hand_shape.transform = minute_hand_transform
        screen.pen = color.rgb(*minute_hand_colour)
        screen.shape(minute_hand_shape)

        second_hand_transform = mat3().translate(64, 64).rotate(self.second_rotation)
        second_hand_transform_shadow = mat3().translate(66, 66).rotate(self.second_rotation)

        second_hand_shape.transform = second_hand_transform_shadow
        screen.pen = shadow
        screen.shape(second_hand_shape)

        second_hand_shape.transform = second_hand_transform
        screen.pen = color.rgb(*second_hand_colour)
        screen.shape(second_hand_shape)

        hour_hand_transform = mat3().translate(64, 64).scale(1.5).rotate(self.hour_rotation)
        hour_hand_transform_shadow = mat3().translate(66, 66).scale(1.5).rotate(self.hour_rotation)

        hour_hand.transform = hour_hand_transform_shadow
        screen.pen = shadow
        screen.shape(hour_hand)

        hour_hand.transform = hour_hand_transform
        screen.pen = color.rgb(*hour_hand_colour)
        screen.shape(hour_hand)


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

    @property
    @micropython.native
    def speed(self):
        return math.sqrt(self.velocity.x ** 2 + self.velocity.y ** 2)

    @micropython.native
    def move(self):
        self.pos += self.velocity

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
def draw_shadows():
    for ball in balls:
        x = ball.pos.x / 100
        y = ball.pos.y / 100
        offset = ball.radius / 250

        screen.pen = shadow
        new_pos = vec2(x + offset, y + offset)
        screen.circle(new_pos, ball.radius / 100)


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

    screen.blit(bg, vec2(0, 0))

    clock.calc_clock()
    seconds_gravity_vec = gravity_vector((clock.second_rotation - 90) % 360)
    minutes_gravity_vec = gravity_vector((clock.minute_rotation - 90) % 360)
    hours_gravity_vec = gravity_vector((clock.hour_rotation - 90) % 360)

    for ball in balls:
        ball.move()
        ball.calc_wall_collisions()

    for combination in ball_combinations:
        calc_ball_collisions(combination[0], combination[1])

    draw_shadows()

    for ball in balls:
        ball.apply_gravity()
        chromeball.draw_ball(ball.pos, ball.radius, ball.colour)

    clock.draw_hands()
    screen.blit(fg, vec2(0, 0))

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
