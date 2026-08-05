import math
import random
import time
import wifi
import ntptime
from machine import RTC

from plugins.gravity_clock_classic import chromeball, timezone
from plugins.gravity_clock_classic.daylightsaving import DaylightSavingPolicy, DaylightSaving

GRAVITY_STRENGTH = 5
seconds_gravity_vec = vec2(0, 0)
minutes_gravity_vec = vec2(0, 0)
hours_gravity_vec = vec2(0, 0)

bg = image.load("/lib/plugins/gravity_clock_classic/assets/bg.png")
fg = image.load("/lib/plugins/gravity_clock_classic/assets/fg.png")

shadow = color.rgb(0, 0, 0, 128)

# These values are exposed to the web interface
hours_colour = (184, 115, 51)  # The colour for the hour balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
minutes_colour = (171, 171, 70)  # The colour for the minute balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
seconds_colour = (96, 96, 96)  # The colour for the second balls. NOTE this is a tuple not a color.rgb because the values are manipulated to get darker and lighter versions, and you can't pull the r, g and b values from a color brush.
hour_hand_colour = color.rgb(184, 115, 51)  # The colour for the hour hand.
minute_hand_colour = color.rgb(220, 200, 82)  # The colour for the minute hand.
second_hand_colour = color.rgb(192, 192, 192)  # The colour for the second hand.
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

screen.antialias = image.X2
screen.font = rom_font.sins


class ClockState:
    Running = 0
    ConnectWiFi = 1
    UpdateTime = 2


month_days = {
    1: 31,
    2: 28,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31
}

calendar_months = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December"
}

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


def update_time(region, timezone):
    # Set the time with ntptime and pass it to the daylight saving calculator.
    # Pass the result to the unit's RTC.

    # handle time out during ntp comms
    try:
        ntptime.settime()
        time.sleep(2)
    except OSError:
        return False

    timezone_minutes = timezone * 60

    hemisphere, week_in, month_in, weekday_in, hour_in, week_out, month_out, weekday_out, hour_out, mins_difference = regions[region]

    dstp = DaylightSavingPolicy(hemisphere, week_in, month_in, weekday_in, hour_in, timezone_minutes + mins_difference)
    stdp = DaylightSavingPolicy(hemisphere, week_out, month_out, weekday_out, hour_out, timezone_minutes)

    dst = DaylightSaving(dstp, stdp)
    t = time.mktime(time.gmtime())
    tm = time.gmtime(dst.localtime(t))
    print(t)
    print(tm)
    rtc = RTC()
    rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))

    return True


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
        self.last_ms = 0

    @micropython.native
    def calc_clock(self):
        currenttime = time.gmtime()
        year, month, day, hour, minute, second, _, _ = currenttime

        if second != self.last_second:
            self.sub_second = 0
            self.last_second = second

        ms = time.ticks_ms()
        ms_diff = time.ticks_diff(ms, self.last_ms)
        self.sub_second += ms_diff
        self.last_ms = ms

        self.second_rotation = (second * 6) + (0.006 * self.sub_second)
        self.minute_rotation = (minute * 6) + (0.1 * second)
        self.hour_rotation = (hour * 30) + (0.5 * minute)

    @micropython.native
    def draw_hands(self):
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
        minute_hand_transform = mat3().translate(64, 64).scale(1.5).rotate(self.minute_rotation)
        minute_hand_transform_shadow = mat3().translate(66, 66).scale(1.5).rotate(self.minute_rotation)

        minute_hand_shape.transform = minute_hand_transform_shadow
        screen.pen = shadow
        screen.shape(minute_hand_shape)

        minute_hand_shape.transform = minute_hand_transform
        screen.pen = minute_hand_colour
        screen.shape(minute_hand_shape)

        second_hand_shape = shape.custom(second_hand_path)
        second_hand_transform = mat3().translate(64, 64).rotate(self.second_rotation)
        second_hand_transform_shadow = mat3().translate(66, 66).rotate(self.second_rotation)

        second_hand_shape.transform = second_hand_transform_shadow
        screen.pen = shadow
        screen.shape(second_hand_shape)

        second_hand_shape.transform = second_hand_transform
        screen.pen = second_hand_colour
        screen.shape(second_hand_shape)

        hour_hand = shape.custom(hour_hand_path)
        hour_hand_transform = mat3().translate(64, 64).scale(1.5).rotate(self.hour_rotation)
        hour_hand_transform_shadow = mat3().translate(66, 66).scale(1.5).rotate(self.hour_rotation)

        hour_hand.transform = hour_hand_transform_shadow
        screen.pen = shadow
        screen.shape(hour_hand)

        hour_hand.transform = hour_hand_transform
        screen.pen = hour_hand_colour
        screen.shape(hour_hand)


class Ball:
    def __init__(self, pos, vel, radius, seconds):
        self.radius = radius
        self.pos = pos
        self.forces = []
        self.velocity = vel
        self.acceleration = vec2(0, 0)
        self.damping = 0.5
        self.pos_correction = vec2(0, 0)
        if seconds == 0:
            self.colour = minutes_colour
        elif seconds == 1:
            self.colour = seconds_colour
        elif seconds == 2:
            self.colour = hours_colour
        self.seconds = seconds
        self.new_velocity = vec2(0, 0)
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
        direction = self.velocity / self.speed
        dot_product = (direction.x * tangent.x) + (direction.y * tangent.y)

        if radius + (self.radius) >= 6000:
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

        screen.pen = color.rgb(0, 0, 0, 128)
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


@micropython.viper
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
clock_state = ClockState.Running

frame_counter = 0


def update():
    global clock_state, seconds_gravity_vec, minutes_gravity_vec, hours_gravity_vec, frametime, last_ticks

    wifi.tick()

    if clock_state == ClockState.Running:
        # If the year in the RTC is 2021 or earlier, we need to sync so it has the same effect as pressing B.
        if time.gmtime()[0] <= 2021:
            print("Time out of joint")
            clock_state = ClockState.ConnectWiFi

            screen.blit(bg, vec2(0, 0))
            clock.draw_hands()
            screen.blit(fg, vec2(0, 0))

            screen.pen = color.white
            screen.text("Updating...", 36, 69)

        else:
            screen.blit(bg, vec2(0, 0))
            draw_shadows()

            clock.calc_clock()
            seconds_gravity_vec = gravity_vector((clock.second_rotation - 90) % 360)
            minutes_gravity_vec = gravity_vector((clock.minute_rotation - 90) % 360)
            hours_gravity_vec = gravity_vector((clock.hour_rotation - 90) % 360)

            for ball in balls:
                chromeball.draw_ball(ball.pos, ball.radius, ball.colour)
                ball.move()
                ball.calc_wall_collisions()

            for combination in ball_combinations:
                calc_ball_collisions(combination[0], combination[1])

            for ball in balls:
                ball.apply_gravity()

            clock.draw_hands()
            screen.blit(fg, vec2(0, 0))

    elif clock_state == ClockState.UpdateTime:
        print("Updating")
        if update_time(timezone.REGION, timezone.TIMEZONE):
            clock_state = ClockState.Running
        print("Updated")

    elif clock_state == ClockState.ConnectWiFi:
        print("Connecting")
        if wifi.connect():
            clock_state = ClockState.UpdateTime
            print("Connected")

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
