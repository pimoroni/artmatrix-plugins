import time
import math

path = [vec2(0, -8),
        vec2(8, -5),
        vec2(12, 1),
        vec2(14, 10),
        vec2(18, 15),
        vec2(20, 20),
        vec2(20, 25),
        vec2(-20, 25),
        vec2(-20, 20),
        vec2(-18, 15),
        vec2(-14, 10),
        vec2(-12, 1),
        vec2(-8, -5)]

blob = shape.custom(path)

eye = shape.circle(0, 0, 7)
pupil = shape.circle(0, 5, 5)


def draw_blob(coords, rotation, colour, anim_offset):
    scale_factor = math.sin((time.ticks_ms() / 150) + anim_offset) / 4
    scaling_x = (1 - scale_factor) / 5
    scaling_y = (1.5 + scale_factor) / 5
    blob_transform = mat3().translate(coords.x, coords.y).rotate(rotation).scale(scaling_x, scaling_y)
    blob.transform = blob_transform
    eye_transform = mat3().translate(coords.x, coords.y).rotate(rotation).scale(0.2, 0.2)
    eye.transform = eye_transform
    pupil.transform = eye_transform
    screen.pen = colour
    screen.shape(blob)
    screen.pen = color.rgb(255, 255, 255)
    screen.shape(eye)
    screen.pen = color.rgb(0, 0, 0)
    screen.shape(pupil)


def draw_blob_flying(coords, rotation, acceleration, colour, anim_offset):
    scaling_factor = 2 * math.sqrt(abs(acceleration.x + acceleration.y))
    scaling_factor = (scaling_factor + (math.sin((time.ticks_ms() / 150) + anim_offset) / 2)) / 4
    scaling_y = 0.75 + min(scaling_factor, 0.5)
    scaling_x = 0.75 - min(scaling_factor, 0.5)

    blob_transform = mat3().translate(coords.x, coords.y).rotate(rotation).scale(scaling_x, scaling_y)
    eye_transform = mat3().translate(coords.x, coords.y).rotate(rotation).scale(0.2, 0.2)
    flying_blob = shape.circle(vec2(0, 0), 5)
    flying_blob.transform = blob_transform
    eye.transform = eye_transform
    pupil.transform = eye_transform
    screen.pen = colour
    screen.shape(flying_blob)
    screen.pen = color.rgb(255, 255, 255)
    screen.shape(eye)
    screen.pen = color.rgb(0, 0, 0)
    screen.shape(pupil)
