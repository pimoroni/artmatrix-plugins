from lsm6ds3 import LSM6DS3, PERFORMANCE_MODE_416HZ
from machine import I2C

screen.antialias = image.X4
cy = screen.height / 2

has_sensor = False

try:
    motion_sensor = LSM6DS3(I2C(), mode=PERFORMANCE_MODE_416HZ)
    has_sensor = True
except OSError:
    pass

CENTRE_X, CENTRE_Y = screen.width / 2, screen.height / 2
samples = []
level = rect(16, 8, screen.width - 32, 28)
screen.font = font.futile
BACKGROUND = color.rgb(238, 170, 2)


def centre_text(text, cy=None, max_size=12, min_size=1, padding=4):

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
    screen.text(text, vec2(cx - tw / 2, cy - th / 2), size)


def update():
    global samples, has_sensor

    if has_sensor:
        # get the sensor readings
        try:
            _, ay, _, _, _, _ = motion_sensor.get_readings()
        except OSError:
            has_sensor = False
            return

        # map to a range of -1.0 to 1.0.
        n = round((((ay - -16383.5) * (1.0 - -1.0)) / (16383.5 - -16383.5)) + -1.0, 1)

        # add our latest value to our samples list and cap it at max 20 values
        samples.append(n)
        samples = samples[-10:]

        # reset clip
        screen.clip = rect(0, 0, screen.width, screen.height)
        screen.pen = BACKGROUND
        screen.clear()

        # draw the surround
        screen.pen = color.black
        screen.shape(shape.rounded_rectangle(level.x - 10, 0, level.w + 20, 56, 0, 0, 3, 3))
        screen.pen = color.smoke
        screen.shape(shape.rounded_rectangle(level.x, 0, level.w, 44, 0, 0, 3, 3))

        # draw the main body of the spirit level
        screen.pen = color.rgb(176, 210, 26, 150)
        screen.shape(shape.rectangle(level.x, level.y, level.w, level.h))

        # draw the logo
        screen.alpha = 150
        screen.pen = color.black
        screen.shape(shape.circle(CENTRE_X + 1, CENTRE_Y + 29, 25))
        screen.shape(shape.circle(CENTRE_X, CENTRE_Y + 28, 16).stroke(1))
        screen.pen = BACKGROUND
        screen.shape(shape.circle(CENTRE_X, CENTRE_Y + 28, 25))
        screen.alpha = 255
        screen.pen = color.black

        # centre logo text
        logo_text = "AM"
        w, _ = screen.measure_text(logo_text)
        x = CENTRE_X - (w / 2)
        screen.text(logo_text, x, CENTRE_Y + 16)

        # get the average from our samples
        offset = sum(samples) / len(samples)
        offset *= level.w / 2

        # set the clip and draw the bubble
        screen.clip = level
        screen.pen = color.rgb(255, 255, 255, 120)
        screen.circle(CENTRE_X + offset, level.y - 6, 15)

        # lines
        screen.pen = color.black
        screen.line(level.x + 32, level.y, level.x + 32, level.y + level.h)
        screen.line(level.x + 64, level.y, level.x + 64, level.y + level.h)
        screen.line(level.x + 30, level.y, level.x + 30, level.y + level.h)
        screen.line(level.x + 66, level.y, level.x + 66, level.y + level.h)

        # shadow and highlights
        screen.pen = color.rgb(0, 0, 0, 75)
        screen.shape(shape.rectangle(level.x, (level.y + level.h) - 2, level.w, 2))
        screen.pen = color.rgb(255, 255, 255, 75)
        screen.shape(shape.rectangle(level.x, level.y, level.w, 2))

        # reset the clip so we don't make a mess of whichever plugin follows this one.
        screen.clip = rect(0, 0, screen.width, screen.height)

    else:
        screen.font = font.salty
        screen.clip = rect(0, 0, screen.width, screen.height)
        screen.pen = color.black
        screen.clear()

        screen.pen = color.red
        centre_text(":(", cy - 35, max_size=3)
        centre_text("Multi Sensor Stick", cy, max_size=3)
        centre_text("not connected.", cy + 20, max_size=3)
