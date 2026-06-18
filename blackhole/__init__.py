import time
import math

CX = screen.width / 2
CY = screen.height / 2

hh = shape.circle(0, 0, 20)
mh = shape.circle(0, 0, 20)
face_outer = shape.circle(0, 0, 55, 4)
time_set = False


def update():

    year, month, day, hour, minute, second, _, _ = time.localtime()

    screen.pen = color.rgb(0, 0, 0)
    screen.clear()

    screen.pen = color.orange
    face_outer.transform = mat3().translate(CX, CY)
    screen.shape(face_outer)

    angle_hour = (hour % 12) * 30
    angle_hour += minute / 2
    screen.pen = color.rgb(255, 255, 255, 150)
    hh.transform = mat3().translate(CX, CY).rotate(angle_hour).translate(0, -45)
    screen.shape(hh)

    angle_minute = minute * 6
    angle_minute += second / 10.0
    screen.pen = color.rgb(0, 0, 0, 200)
    mh.transform = mat3().translate(CX, CY).rotate(angle_minute).translate(0, -45)
    screen.shape(mh)

    screen.blur(5)

    screen.pen = color.rgb(0, 0, 0, 75)
    c = 4
    for n in range(256):
        a = n * 10
        r = c * math.sqrt(n)

        x = int(r * math.cos(a) + screen.width // 2)
        y = int(r * math.sin(a) + screen.height // 2)

        screen.circle(x, y, 2)

    screen.blur(0.1)

    screen.pen = color.rgb(0, 0, 0)
    screen.shape(shape.circle(CX, CY, 35, 2))

    screen.pen = color.white
    screen.shape(shape.circle(CX, CY, 35, 2).stroke(1))

    display.update()
