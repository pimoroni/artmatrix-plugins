import math
import time
from random import uniform

from breakout_bme280 import BreakoutBME280
from machine import I2C

screen.antialias = image.X2

galileo_bg = brush.gradient(brush.LINEAR, 0, 0, 0, screen.height,
                            ((0.0, color.rgb(38, 92, 128)), (1.0, color.rgb(12, 34, 62))))

has_sensor = False

CX = screen.width / 2
CY = screen.height / 2
ORB_RADIUS = 12
MIN_Y = ORB_RADIUS
MAX_Y = screen.height - ORB_RADIUS
MID = (MIN_Y + MAX_Y) / 2
TRAVEL = (MAX_Y - MIN_Y) / 2
RANGE = 7
SMOOTHING = 0.001
GAP = 30

# list of the orbs in the therm
orbs = [
    {"temperature": 16, "colour": color.rgb(128, 90, 220), "x": CX - 50, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 18, "colour": color.rgb(178, 95, 205), "x": CX - 33, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 20, "colour": color.rgb(225, 95, 165), "x": CX - 17, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 22, "colour": color.rgb(245, 225, 70), "x": CX, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 24, "colour": color.rgb(245, 185, 60), "x": CX + 17, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 26, "colour": color.rgb(240, 130, 50), "x": CX + 33, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
    {"temperature": 28, "colour": color.rgb(232, 80, 58), "x": CX + 50, "y": CY, "bob_offset": uniform(0, 2 * math.pi)},
]

try:
    temperature_sensor = BreakoutBME280(I2C())
    has_sensor = True
except OSError:
    pass


def centre_text(text, cy=None, max_size=12, min_size=1, padding=4, colour=color.rgb(255, 255, 255)):

    max_width = screen.width - padding * 2
    size = max_size
    while size > min_size:
        tw, th = screen.measure_text(text, size)
        if tw <= max_width:
            break
        size -= 1
    tw, th = screen.measure_text(text, size)
    cx = screen.width / 2
    if cy is None:
        cy = screen.height / 2

    screen.pen = color.rgb(0, 0, 0, 100)
    screen.text(text, vec2((cx - tw / 2) + 2, (cy - th / 2) + 2), size)

    screen.pen = colour
    screen.text(text, vec2(cx - tw / 2, cy - th / 2), size)


last_reading = None
readings = []


def get_reading():
    global last_reading, has_sensor

    try:
        reading = temperature_sensor.read()
        last_reading = time.ticks_ms()

        # round the readings to 1 decimal place
        reading = [round(r, 1) for r in reading]

        # unpack the readings into sensible variables
        temp, pressure, humidity = reading

        readings.append(temp)

        if len(readings) > 10:
            readings.pop(0)

    except RuntimeError:
        has_sensor = False

    # return the current average
    return sum(readings) / len(readings) if readings else None


current_temp = None


def update():
    global current_temp

    # tiiiiime for animations
    t = time.ticks_ms() / 1000

    # clear the screen with the gradient
    screen.pen = galileo_bg
    screen.clear()

    # time since last reading from the sensor
    time_since_last = time.ticks_diff(time.ticks_ms(), last_reading) / 1000

    if has_sensor:

        screen.font = font.ignore

        if last_reading is None or time_since_last > 2:
            read = get_reading()
            if read is not None:
                current_temp = round(read)

        if current_temp is not None:
            for orb in orbs:
                # cal the time diff
                temp_diff = orb["temperature"] - current_temp

                # clamp between 0 and 1
                temp_diff_norm = min(1, abs(temp_diff) / RANGE)

                # move it above or below the gap, depending on the temperature.
                if temp_diff >= 0:
                    target = MID - GAP - temp_diff_norm * (TRAVEL - GAP)
                else:
                    target = MID + GAP + temp_diff_norm * (TRAVEL - GAP)

                # move towards target position
                orb["y"] += (target - orb["y"]) * SMOOTHING

                # bobbing around like a buoy!
                x = orb["x"] + math.sin((t + orb["bob_offset"])) * 2.0
                y = orb["y"] + math.cos((t + orb["bob_offset"])) * 3.0

                # draw the things
                screen.pen = orb["colour"]
                screen.shape(shape.circle(x, y, ORB_RADIUS))
                screen.pen = color.rgb(255, 255, 255, 75)
                screen.shape(shape.circle(x - 5, y - 6, ORB_RADIUS / 4))

            centre_text(f"{current_temp}°")

    else:
        screen.font = font.salty
        screen.clip = rect(0, 0, screen.width, screen.height)
        screen.pen = color.black
        screen.clear()

        screen.pen = color.red
        centre_text(":(", CY - 35, max_size=3)
        centre_text("Multi Sensor Stick", CY, max_size=3)
        centre_text("not connected.", CY + 20, max_size=3)
