import errno
import json
import math
import os
import random
import time

import config
import micropython
import ubinascii

from easing import easeOutSine
from plugin_config import plugin_config

# main.py mounts the card at /sd during boot, if there is one
sd_present = "sd" in os.listdir("/")

cfg = plugin_config("art_matrix_show", {
    "storage": "sd" if sd_present else "internal",
    "duration": 10,
    "order": "in_order",
    "transition": "fizzle",
})
storage = cfg["storage"]
duration = cfg["duration"]  # seconds per picture

# for the page, in the biggest unit it divides into
if duration % 3600 == 0:
    duration_value, duration_unit = duration // 3600, "hours"
elif duration % 60 == 0:
    duration_value, duration_unit = duration // 60, "minutes"
else:
    duration_value, duration_unit = duration, "seconds"
order = cfg["order"]
transition = cfg["transition"]

FOLDERS = {"sd": "/sd/art_matrix_show", "internal": "/lib/plugins/art_matrix_show/pictures"}
PLACE_NAMES = {"sd": "the SD card", "internal": "internal storage"}
LIMITS = {"sd": 30, "internal": 5}

SETTINGS = ("storage", "duration", "order", "transition")

# main.py reloads the plugin after every post to its page, so where the
# slideshow had got to is passed across in this
SHOWING_FILE = "/lib/plugins/art_matrix_show/showing.json"

TRANSITION_MS = 1000

# the next picture loads once this one has been up this long. a ~200ms load
# from the card can't be seen while the screen is still
PRELOAD_AFTER_MS = 2000
TRANSITIONS = ("fizzle", "slide", "bars", "star")

# the sides a slide can come in from, as a step in x and y. each one picks at random
SLIDE_STEPS = ((0, -1), (0, 1), (-1, 0), (1, 0))

BAR_WIDTH = 16

# the star's inner points have to pass the corners, 91px out, before the
# screen is covered. inner is half of outer, so outer has to reach 182
STAR_REACH = 184


def list_pictures(place):
    try:
        names = sorted(name for name in os.listdir(FOLDERS[place]) if name.endswith(".jpg"))
    except OSError:
        # no folder yet, or no card
        return []
    try:
        with open(f"{FOLDERS[place]}/order.json") as file:
            order = json.load(file)
    except (OSError, ValueError):
        # never rearranged, so upload order
        return names
    # rearranged ones in their place, anything uploaded since on the end
    return [name for name in order if name in names] + [name for name in names if name not in order]


storage_ready = storage == "internal" or sd_present
pictures = list_pictures(storage) if storage_ready else []

other_place = "internal" if storage == "sd" else "sd"
other_count = len(list_pictures(other_place))
if other_count:
    other_note = f"{other_count} more on {PLACE_NAMES[other_place]}. Switch to it to see them."
else:
    other_note = ""


def gallery():
    # the template engine streams a generator, so only one picture is in memory at a time
    for name in pictures:
        with open(f"{FOLDERS[storage]}/{name}", "rb") as file:
            encoded = ubinascii.b2a_base64(file.read(), newline=False).decode()
        yield f'<div class="picture"><img src="data:image/jpeg;base64,{encoded}" alt="" draggable="false"><button type="button" class="icon delete" data-name="{name}" aria-label="Delete picture"></button></div>'


def make_folder(place):
    try:
        os.mkdir(FOLDERS[place])
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise


def process_config(form):
    # remember where the slideshow is, main.py reloads the plugin after this
    if pictures:
        with open(SHOWING_FILE, "w") as file:
            json.dump([pictures[picture_index], picture_index], file)

    # delete, arrange and upload posts carry only their own fields, settings stay put
    if "delete" in form:
        if form["delete"] in pictures:
            os.remove(f"{FOLDERS[storage]}/{form['delete']}")
        return

    if "arrange" in form:
        if pictures:
            with open(f"{FOLDERS[storage]}/order.json", "w") as file:
                json.dump([name for name in form["arrange"].split(",") if name in pictures], file)
        return

    if "picture" in form:
        # named by the phone's clock. a move or zoom resends it under the same name
        name = form.get("name", "")
        has_room = name in pictures or len(pictures) < LIMITS[storage]
        if storage_ready and name.endswith(".jpg") and name[:-4].isdigit() and has_room:
            # base64url, so the post has no %-escapes, which phew decodes slowly
            encoded = form["picture"].replace("-", "+").replace("_", "/")
            encoded += "=" * (-len(encoded) % 4)
            make_folder(storage)
            with open(f"{FOLDERS[storage]}/{name}", "wb") as file:
                file.write(ubinascii.a2b_base64(encoded))
            # new ones go on the end, so the order is arrival order, not clock order
            if name not in pictures:
                with open(f"{FOLDERS[storage]}/order.json", "w") as file:
                    json.dump(pictures + [name], file)
        return

    settings = {key: form[key] for key in SETTINGS if key in form}
    with open("/lib/plugins/art_matrix_show/config.json", "w") as file:
        json.dump(settings, file)

    new_storage = settings.get("storage", storage)
    if new_storage == storage or (new_storage == "sd" and not sd_present):
        return

    # a move stops at the limit, the rest stay where they were
    make_folder(new_storage)
    already_there = list_pictures(new_storage)
    to_move = list_pictures(storage)[:max(LIMITS[new_storage] - len(already_there), 0)]
    for name in to_move:
        old_path = f"{FOLDERS[storage]}/{name}"
        with open(old_path, "rb") as file:
            data = file.read()
        with open(f"{FOLDERS[new_storage]}/{name}", "wb") as file:
            file.write(data)
        os.remove(old_path)

    # the arranged order comes along, after any already there
    with open(f"{FOLDERS[new_storage]}/order.json", "w") as file:
        json.dump(already_there + to_move, file)


@micropython.viper
def reveal_pixels(target, source, state: int, count: int) -> int:
    # steps a 14-bit lfsr, which visits every pixel but 0 once in a scattered
    # order, copying each one it lands on. returns where it got to
    target_pixels = ptr32(target)
    source_pixels = ptr32(source)
    revealed = 0
    while revealed < count:
        low_bit = state & 1
        state = state >> 1
        if low_bit:
            state = state ^ 0x3802
        target_pixels[state] = source_pixels[state]
        revealed += 1
    return state


try:
    with open(SHOWING_FILE) as file:
        showing_name, showing_index = json.load(file)
    # only bridges a reload, a reboot starts from the beginning
    os.remove(SHOWING_FILE)
except (OSError, ValueError):
    showing_name, showing_index = None, 0

if showing_name in pictures:
    picture_index = pictures.index(showing_name)
elif pictures:
    # it was deleted, so carry on with the one that took its place
    picture_index = min(showing_index, len(pictures) - 1)
else:
    picture_index = 0
current_picture = image.load(f"{FOLDERS[storage]}/{pictures[picture_index]}") if pictures else None
previous_picture = None
# loaded ahead of the change, see PRELOAD_AFTER_MS
next_index = None
next_picture = None

shown_at = time.ticks_ms()

transition_start = None
running_transition = None
slide_step = None
star_brush = None

# fizzle builds up on its own canvas, made the first time it's needed
fizzle_canvas = None
# where the lfsr has got to, and how many pixels it has shown
fizzle_state = 1
fizzle_revealed = 0


def update():
    global picture_index, current_picture, previous_picture, next_index, next_picture, shown_at, transition_start
    global running_transition, slide_step, star_brush, fizzle_canvas, fizzle_state, fizzle_revealed

    now = time.ticks_ms()

    if current_picture is None:
        screen.pen = color.rgb(0, 0, 0)
        screen.clear()
        screen.font = font.smart
        lines = (
            ("No pictures yet" if storage_ready else "SD card missing", color.red),
            ("visit", color.blue),
            (f"{config.wifi_hostname}.local", color.white),
            ("to add some" if storage_ready else "or switch storage", color.blue),
        )
        sizes = [screen.measure_text(line, 1) for line, pen in lines]
        # 8px between lines, the whole block centred
        block_height = sum(int(height) for width, height in sizes) + 8 * (len(lines) - 1)
        y = (screen.height - block_height) // 2
        for (line, pen), (width, height) in zip(lines, sizes):
            screen.pen = pen
            screen.text(line, int(screen.width - width) // 2, y, 1)
            y += int(height) + 8
        return

    if transition_start is None and len(pictures) > 1:
        shown_for = time.ticks_diff(now, shown_at)

        if next_picture is None and shown_for >= PRELOAD_AFTER_MS:
            if order == "shuffle":
                next_index = random.choice([index for index in range(len(pictures)) if index != picture_index])
            else:
                next_index = (picture_index + 1) % len(pictures)
            next_picture = image.load(f"{FOLDERS[storage]}/{pictures[next_index]}")

        if next_picture is not None and shown_for >= duration * 1000:
            picture_index = next_index
            previous_picture = current_picture
            current_picture = next_picture
            next_picture = None
            shown_at = now

            if transition != "none":
                running_transition = random.choice(TRANSITIONS) if transition == "random" else transition
                slide_step = random.choice(SLIDE_STEPS)
                transition_start = now

                if running_transition == "star":
                    # the image brush lands a pixel left of blit, which shows as a
                    # jump when the transition ends. half a pixel right lines them up
                    star_brush = brush.image(current_picture, mat3().translate(0.5, 0))
                elif running_transition == "fizzle":
                    if fizzle_canvas is None:
                        fizzle_canvas = image(screen.width, screen.height)
                    memoryview(fizzle_canvas)[:] = memoryview(previous_picture)
                    fizzle_state = 1
                    fizzle_revealed = 0

    if transition_start is not None:
        progress = time.ticks_diff(now, transition_start) / TRANSITION_MS
        if progress >= 1:
            transition_start = None
            previous_picture = None
            star_brush = None

    if transition_start is None:
        screen.blit(current_picture, 0, 0)
        return

    # every transition comes in quickly and slows to a stop
    eased_progress = easeOutSine(progress)

    if running_transition == "slide":
        step_x, step_y = slide_step
        incoming_x = int(step_x * screen.width * (1 - eased_progress))
        incoming_y = int(step_y * screen.height * (1 - eased_progress))
        screen.blit(previous_picture, incoming_x - step_x * screen.width, incoming_y - step_y * screen.height)
        screen.blit(current_picture, incoming_x, incoming_y)
    elif running_transition == "bars":
        screen.blit(previous_picture, 0, 0)
        bar_width = math.ceil(eased_progress * BAR_WIDTH)
        if bar_width:
            for bar_x in range(0, screen.width, BAR_WIDTH):
                bar = rect(bar_x, 0, bar_width, screen.height)
                screen.blit(current_picture, bar, bar)
    elif running_transition == "star":
        screen.blit(previous_picture, 0, 0)
        star_radius = eased_progress * STAR_REACH
        screen.pen = star_brush
        screen.shape(shape.star(vec2(screen.width / 2, screen.height / 2), 5, star_radius, star_radius / 2))
    else:
        pixels_due = int(eased_progress * 16383)
        fizzle_state = reveal_pixels(memoryview(fizzle_canvas), memoryview(current_picture), fizzle_state, pixels_due - fizzle_revealed)
        fizzle_revealed = pixels_due
        screen.blit(fizzle_canvas, 0, 0)
