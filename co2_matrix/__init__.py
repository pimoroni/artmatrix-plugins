from breakout_scd41 import BreakoutSCD41
from machine import I2C

# centres
CX = screen.width / 2
CY = screen.height / 2

CO2_MIN = 400
CO2_MAX = 2000
has_sensor = False

screen.font = font.ignore

try:
    sensor = BreakoutSCD41(I2C())
    sensor.start()
    has_sensor = True
except RuntimeError:
    pass


def centre_text(text, cy=None, max_size=12, min_size=1, padding=4, colour=color.white):

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

    screen.pen = color.rgb(0, 0, 0, 200)
    screen.text(text, vec2((cx - tw / 2) + 2, (cy - th / 2) + 2), size)

    screen.pen = colour
    screen.text(text, vec2(cx - tw / 2, cy - th / 2), size)


def update():
    global has_sensor

    if has_sensor:

        screen.font = font.ignore

        try:
            if not sensor.ready():
                return

            co2_raw, _, _ = sensor.measure()
            co2_clamped = min(CO2_MAX, max(co2_raw, CO2_MIN))
            co2_norm = (co2_clamped - CO2_MIN) / (CO2_MAX - CO2_MIN)

            # we want to start at green, not red!
            hue = 0.33 * ((1.0 - co2_norm) * 255)

            # set the bg colour
            screen.pen = color.hsv(hue, 255, 255)
            screen.clear()

            # darken the display edges
            screen.pen = brush.vignette(350)
            screen.clear()

            # grid on grid!
            screen.pen = brush.grid(4, 35)
            screen.clear()

            # draw the text over the top, we don't want the grid over the text
            centre_text(f"{co2_raw:.0f}", cy=CY - 10, max_size=2)
            centre_text("PPM", cy=CY + 20, max_size=1)
        except RuntimeError:
            has_sensor = False

    else:
        screen.font = font.salty
        screen.clip = rect(0, 0, screen.width, screen.height)
        screen.pen = color.black
        screen.clear()

        screen.pen = color.red
        centre_text(":(", CY - 35, max_size=3)
        centre_text("SCD41 CO2 Sensor", CY, max_size=3)
        centre_text("not connected.", CY + 20, max_size=3)
