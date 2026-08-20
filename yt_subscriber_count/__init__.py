import json
from lib.fetch import AsyncFetch
from random import randint, uniform, choice

API_UPDATE_TIME = 60
API_HOST = "www.googleapis.com"
DATA_PATH = "/lib/plugins/yt_subscriber_count"

palette = []
# grab all the built in colours
for c in dir(color):
    ob = getattr(color, c)
    if isinstance(ob, color):
        palette.append(ob)

api_key = None
channel_id = None
channel_name_colour = (255, 0, 0)
subscriber_count_colour = (255, 255, 255)
background_colour = (0, 0, 0)
animate_background = True
has_details = False

sub_count = None
last_sub_count = None
account_name = None

confetti = False
confetti_particles = []

cy = screen.height / 2
cx = screen.width / 2


def hex_to_rgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


try:
    with open(f"{DATA_PATH}/config.json") as file:
        config_file = json.load(file)
        api_key = config_file["api_key"] or None
        channel_id = config_file["channel_id"] or None
        has_details = True if api_key and channel_id else False

        channel_name_colour = hex_to_rgb(config_file["channel_name_colour"])
        subscriber_count_colour = hex_to_rgb(config_file["subscriber_count_colour"])
        background_colour = hex_to_rgb(config_file["background_colour"])
        animate_background = "animate_background" in config_file
except OSError:
    pass
except KeyError:
    pass


if has_details:
    API_PATH = f"/youtube/v3/channels?part=statistics,snippet&id={channel_id}&key={api_key}"
    api_data = AsyncFetch(API_HOST, 443, use_tls=True, debug=True)
    api_data.fetch(API_PATH, interval=API_UPDATE_TIME)

    @api_data.on_complete
    def process_data(fetch):
        global data, account_name, sub_count, last_sub_count

        last_sub_count = sub_count
        data = fetch.to_json()
        account_name = data["items"][0]["snippet"]["title"]
        sub_count = int(data["items"][0]["statistics"]["subscriberCount"])

    @api_data.on_error
    def process_fail(fetch):
        return True


def format_num(n):
    length = len(str(n))
    if length < 4:
        return str(n)
    if length > 3 and length < 7:
        n /= 1000
        return "{:.1f}K".format(n)
    if length > 6 and length < 10:
        n /= 1000000
        return "{:.1f}M".format(n)
    if length >= 10:
        n /= 1000000000
        return "{:.1f}B".format(n)


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
            for p in particles:
                p[1] -= p[2]
                if p[1] < 0 - p[3]:
                    p[1] = screen.height
                    p[0] = randint(1, screen.width - 1)

                screen.rectangle(p[0], p[1], p[3], p[3])
            screen.blur(1.0)

        if sub_count:

            if last_sub_count and sub_count > last_sub_count and not confetti:
                confetti = True
                last_sub_count = sub_count

                for _ in range(100):
                    x = cx
                    y = cy
                    vy = uniform(-2.0, 2.0)
                    vx = uniform(-2.0, 2.0)
                    age = 100
                    colour = choice(palette)
                    confetti_particles.append([x, y, vx, vy, age, colour])

            screen.pen = channel_colour
            centre_text(account_name, cy - 30, 28)
            screen.pen = subscriber_colour
            centre_text(format_num(sub_count), cy, 72)
            screen.pen = channel_colour
            centre_text("Subscribers", cy + 30, 28)
        else:
            centre_text("loading")

        if confetti:
            for p in confetti_particles[:]:
                p[3] += 0.05   # gravity
                p[0] += p[2]
                p[1] += p[3]
                p[4] -= 1
                if p[4] <= 0:
                    confetti_particles.remove(p)

                screen.pen = p[5]
                screen.rectangle(p[0], p[1], 2, 2)

            if len(confetti_particles) == 0:
                confetti = False
    else:
        screen.pen = color.black
        screen.clear()
        screen.pen = color.red
        centre_text("Setup needed", cy - 50)
        screen.pen = color.blue
        centre_text("visit", cy - 10, 1)
        screen.pen = color.white
        centre_text("artmatrix.local", cy + 5, 2)
        screen.pen = color.blue
        centre_text("to configure", cy + 40, 1)
        centre_text("plugin", cy + 50, 1)
