import time

from plugin_config import plugin_config

cfg = plugin_config("art_matrix_write", {
    "message": "Hello from Art Matrix!",
    "font_name": "sins",
    "direction": "left",
    "position": "middle",
    "background": (0, 0, 0),
    "colour": (255, 255, 255),
    "effect": "solid",
    "drop_shadow": True,
    "wobble": False,
    "zoom": False,
    "edge_glow": False,
    "chromatic": False,
    "glitch": False,
    "glow": False,
    "crt": False,
    "palette": "none",
    "size": 2,
    "speed": 32,
})
message = cfg["message"]
font_name = cfg["font_name"]
direction = cfg["direction"]
position = cfg["position"]
background = cfg["background"]
colour = cfg["colour"]
effect = cfg["effect"]
drop_shadow = cfg["drop_shadow"]
wobble = cfg["wobble"]
zoom = cfg["zoom"]
edge_glow = cfg["edge_glow"]
chromatic = cfg["chromatic"]
glitch = cfg["glitch"]
glow = cfg["glow"]
crt = cfg["crt"]
palette = cfg["palette"]
size = cfg["size"]
speed = cfg["speed"]  # px per second

# blank pause between scrolling messages
GAP_MS = 500

# how long static text shows each message
HOLD_MS = 5000

# room between wrapped lines, 1 has them touching. keep it to quarters, they
# add up exactly in floats. others drift and can knock a line up a pixel
LINE_SPACING = 1.25

# frames timed per speed check. the median ignores one slow frame like a gc sweep
MEASURE_FRAMES = 15

# a new step has to be this much closer to the speed asked for before it's used,
# so a frame time sitting between two steps can't flip it back and forth
SWITCH_MARGIN = 0.2

# one message per line, blank lines skipped
messages = [line.strip() for line in message.splitlines() if line.strip()]
if not messages:
    messages = ["Hello from Art Matrix!"]

font_face = getattr(font, font_name)

# the shadow sits one pixel down and right per size step
shadow_offset = size if drop_shadow else 0

background_colour = color.rgb(*background)
solid_text_colour = color.rgb(*colour)
solid_shadow_colour = color.rgb(*(channel // 4 for channel in colour))

# scrolling text stays hidden until the first frames are timed. a guess
# would start at the wrong speed and then correct itself
move_px = None
move_every = 1
checks_done = 0
frame_count = 0
frame_gaps = []
last_frame = None
text_shown = False

message_index = -1
message_hue = 0


def start_next_message():
    global message_index, current_text, message_hue, text_width, text_height, text_y, words, scrolled, gap_ends, hold_ends
    message_index = (message_index + 1) % len(messages)
    current_text = messages[message_index]
    # rainbow gives each message its own hue
    message_hue = (message_hue + 48) % 256

    screen.font = font_face
    if direction == "left":
        width, height = screen.measure_text(current_text, size)
        # measure_text gives floats, the text only lands on whole pixels
        text_width = int(width)
        text_height = int(height)
    else:
        # wrapped and centred like film credits. split into words once here,
        # not every frame
        words = text.tokenise(screen, current_text, size=size)
        # drawn once off screen to find how tall the wrapped block is
        offscreen = rect(0, screen.height, screen.width, screen.height)
        text_height = int(text.draw(screen, words, offscreen, size=size, align="center", line_spacing=LINE_SPACING).h)

    if position == "top":
        text_y = 0
    elif position == "middle":
        text_y = (screen.height - text_height) // 2
    else:
        # lifted so the shadow stays on screen, plus 1px the panel's frame covers
        text_y = screen.height - text_height - shadow_offset - 1

    # how far the text has moved, in pixels
    scrolled = 0
    gap_ends = time.ticks_add(time.ticks_ms(), GAP_MS)
    hold_ends = time.ticks_add(time.ticks_ms(), HOLD_MS)


start_next_message()


def update():
    global move_px, move_every, checks_done, frame_count, frame_gaps, last_frame, text_shown, scrolled
    screen.pen = background_colour
    screen.clear()

    # time recent frames and pick the step that keeps the speed steady
    now = time.ticks_ms()
    # the blank gap between messages is quicker to draw, so once there's a step
    # only frames that had text on them count. text_shown is still last frame's
    if last_frame is not None and (move_px is None or text_shown):
        frame_gaps.append(time.ticks_diff(now, last_frame))
    last_frame = now
    if len(frame_gaps) == MEASURE_FRAMES:
        frame_gaps.sort()
        frame_ms = frame_gaps[MEASURE_FRAMES // 2]
        frame_gaps = []
        # whole pixels every frame, or one pixel every few frames. anything in
        # between, like 1.5, moves 1 then 2 and judders
        ideal_px = speed * frame_ms / 1000
        if ideal_px >= 1:
            best_px, best_every = round(ideal_px), 1
        else:
            best_px, best_every = 1, round(1 / ideal_px)
        best_error = abs(best_px / best_every - ideal_px) / ideal_px
        checks_done += 1
        # the first check runs before any text is drawn, so its frames are quick
        # and the step it picks is too small. the second check always replaces it
        if checks_done <= 2:
            move_px, move_every = best_px, best_every
        else:
            move_error = abs(move_px / move_every - ideal_px) / ideal_px
            if move_error - best_error > SWITCH_MARGIN:
                move_px, move_every = best_px, best_every

    # static text doesn't need a speed or gap check
    text_shown = direction == "static" or (move_px is not None and time.ticks_diff(now, gap_ends) >= 0)
    if text_shown:
        if effect == "solid":
            text_colour = solid_text_colour
            shadow_colour = solid_shadow_colour
        else:
            if effect == "cycle":
                # all the way round in ~10s
                hue = (now // 40) % 256
            else:
                hue = message_hue
            # same lightness for every hue, fit() trims chroma to what sRGB can show
            text_colour = color.oklch(190, 255, hue).fit()
            shadow_colour = color.oklch(80, 255, hue).fit()

        screen.font = font_face

        if direction != "static":
            # stepped by frames, not placed by the clock, which jittered
            frame_count += 1
            if frame_count % move_every == 0:
                scrolled += move_px

        if direction == "left":
            text_x = screen.width - scrolled
            if drop_shadow:
                screen.pen = shadow_colour
                screen.text(current_text, text_x + shadow_offset, text_y + shadow_offset, size)
            screen.pen = text_colour
            screen.text(current_text, text_x, text_y, size)
            finished = text_x + text_width + shadow_offset <= 0
        else:
            if direction == "up":
                text_top = screen.height - scrolled
                finished = text_top + text_height + shadow_offset <= 0
            else:
                text_top = text_y
                # a lone message just stays, so a rainbow hue doesn't jump
                finished = len(messages) > 1 and time.ticks_diff(now, hold_ends) >= 0
            if drop_shadow:
                screen.pen = shadow_colour
                shadow_bounds = rect(shadow_offset, text_top + shadow_offset, screen.width, text_height)
                text.draw(screen, words, shadow_bounds, size=size, align="center", line_spacing=LINE_SPACING)
            screen.pen = text_colour
            bounds = rect(0, text_top, screen.width, text_height)
            text.draw(screen, words, bounds, size=size, align="center", line_spacing=LINE_SPACING)

        if finished:
            start_next_message()

    # warps first, edge glow before the other glows, then the palette, and
    # scanlines last so nothing fills them in
    if wobble:
        screen.wave(0, 3)
    if zoom:
        screen.zoom(200)
    if edge_glow:
        screen.edgeglow(220)
    if chromatic:
        screen.chromatic(1)
    if glitch:
        screen.glitch(40)
    if glow:
        screen.bloom(80, 220, 4)

    # each palette recolours the whole screen, so only one at a time
    if palette == "synthwave":
        screen.synthwave()
    elif palette == "gameboy":
        screen.gameboy()
    elif palette == "nightvision":
        screen.nightvision()

    if crt:
        screen.crt(2, 70)
