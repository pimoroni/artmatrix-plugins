from fetch import AsyncFetch
from random import randint, uniform, choice

from plugin_config import plugin_config
from qr_screen import draw_qr_screen
from scrolling import Scroll

API_UPDATE_TIME = 60
API_HOST = "www.googleapis.com"

cfg = plugin_config("yt_subscriber_count", {
    "api_key": None,
    "channel_id": None,
    "channel_name_colour": (255, 0, 0),
    "subscriber_count_colour": (255, 255, 255),
    "background_colour": (0, 0, 0),
    "animate_background": True,
})
api_key = cfg["api_key"]
channel_id = cfg["channel_id"]
channel_name_colour = cfg["channel_name_colour"]
subscriber_count_colour = cfg["subscriber_count_colour"]
background_colour = cfg["background_colour"]
animate_background = cfg["animate_background"]
has_details = bool(api_key and channel_id)

sub_count = None
last_sub_count = None
shown_channel = None

confetti = False
confetti_particles = []

centre_y = screen.height / 2
centre_x = screen.width / 2

TEXT_WIDTH = screen.width - 8
ROW_GAP = 2
SCROLL_GAP = 24
CONFETTI_CONTRAST = 2


if has_details:
    channel = channel_id.strip()
    if len(channel) == 24 and channel.startswith("UC"):
        lookup = f"id={channel}"
    else:
        handle = "".join("%%%02X" % byte if byte > 127 or byte == 32 else chr(byte) for byte in channel.encode())
        lookup = f"forHandle={handle}"
    API_PATH = f"/youtube/v3/channels?part=statistics,snippet&{lookup}&key={api_key}"
    api_data = AsyncFetch(API_HOST, 443, use_tls=True, debug=True)
    api_data.fetch(API_PATH, interval=API_UPDATE_TIME)

    @api_data.on_complete
    def process_data(fetch):
        global sub_count, last_sub_count, rows, shown_channel

        data = fetch.to_json()
        if not data.get("items"):
            show_message("No such channel")
            return
        channel = data["items"][0]
        if channel["statistics"].get("hiddenSubscriberCount"):
            show_message("Count hidden")
            return

        last_sub_count = sub_count
        sub_count = int(channel["statistics"]["subscriberCount"])
        name = channel["snippet"]["title"]
        # a new layout restarts a scrolling name
        if (name, sub_count) == shown_channel:
            return
        shown_channel = (name, sub_count)
        # salty grows 17px a size. these caps keep all three rows on the screen
        rows = layout_rows((
            (name, 2, channel_colour),
            (format_num(sub_count), 3, subscriber_colour),
            ("Subscribers", 1, channel_colour),
        ))

    @api_data.on_error
    def process_fail(fetch):
        if fetch.http_status in (400, 403):
            show_message("Check API key")
        return True


# rounds down to 3 significant figures like youtube does
def format_num(count):
    if count < 1000:
        return str(count)
    divisor, suffix = 1000, "K"
    if count >= 1000000000:
        divisor, suffix = 1000000000, "B"
    elif count >= 1000000:
        divisor, suffix = 1000000, "M"

    hundredths = count * 100 // divisor
    whole = hundredths // 100
    if whole < 10:
        text = f"{whole}.{hundredths % 100:02d}"
    elif whole < 100:
        text = f"{whole}.{hundredths // 10 % 10}"
    else:
        return f"{whole}{suffix}"
    return text.rstrip("0").rstrip(".") + suffix


# rows are (text, max size, colour). each shrinks to fit the width, then they stack centred
def layout_rows(rows):
    fitted = []
    total_height = ROW_GAP * (len(rows) - 1)
    for text, size, colour in rows:
        width, height = screen.measure_text(text, size)
        while width > TEXT_WIDTH and size > 1:
            size -= 1
            width, height = screen.measure_text(text, size)
        fitted.append((text, size, colour, width, height))
        total_height += height

    placed = []
    y = (screen.height - total_height) / 2
    for text, size, colour, width, height in fitted:
        scroll = None
        # still too wide at size 1
        if width > TEXT_WIDTH:
            scroll = Scroll(text, font_face=font.salty, gap=SCROLL_GAP, align=int(y))
        placed.append((text, vec2((screen.width - width) / 2, y), size, colour, scroll))
        y += height + ROW_GAP
    return placed


def show_message(text):
    global rows, shown_channel

    rows = layout_rows(((text, 2, channel_colour),))
    shown_channel = None


# Create the particles list
particles = []
for _ in range(100):
    x = randint(1, screen.width - 1)
    y = randint(0, screen.height - 1)
    size = randint(1, 5)
    speed = uniform(0.1, 0.5)
    particles.append([x, y, speed, size])


# Unpack the tuples into a color object
channel_colour = color.rgb(*channel_name_colour)
subscriber_colour = color.rgb(*subscriber_count_colour)
bg_colour = color.rgb(*background_colour)

palette = []
# grab the built in colours that show up on the background
for colour_name in dir(color):
    named_colour = getattr(color, colour_name)
    if isinstance(named_colour, color) and named_colour.a and named_colour.contrast(bg_colour) >= CONFETTI_CONTRAST:
        palette.append(named_colour)

screen.font = font.salty
show_message("loading")


def update():
    global confetti, last_sub_count

    screen.font = font.salty

    screen.pen = bg_colour
    screen.clear()

    if has_details:
        api_data.update()

        screen.pen = channel_colour
        if animate_background:
            # Background particles
            for particle in particles:
                particle[1] -= particle[2]
                if particle[1] < 0 - particle[3]:
                    particle[1] = screen.height
                    particle[0] = randint(1, screen.width - 1)

                screen.rectangle(particle[0], particle[1], particle[3], particle[3])
            screen.blur(1.0)

        if last_sub_count and sub_count > last_sub_count and not confetti:
            confetti = True
            last_sub_count = sub_count

            for _ in range(100):
                x = centre_x
                y = centre_y
                speed_y = uniform(-2.0, 2.0)
                speed_x = uniform(-2.0, 2.0)
                age = 100
                colour = choice(palette)
                confetti_particles.append([x, y, speed_x, speed_y, age, colour])

        for text, position, size, colour, scroll in rows:
            screen.pen = colour
            if scroll:
                scroll()
            else:
                screen.text(text, position, size)

        if confetti:
            for piece in confetti_particles[:]:
                piece[3] += 0.05   # gravity
                piece[0] += piece[2]
                piece[1] += piece[3]
                piece[4] -= 1
                if piece[4] <= 0:
                    confetti_particles.remove(piece)

                screen.pen = piece[5]
                screen.rectangle(piece[0], piece[1], 2, 2)

            if len(confetti_particles) == 0:
                confetti = False
    else:
        draw_qr_screen("YouTube", "Setup needed", "yt_subscriber_count")
