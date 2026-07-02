from fetch import AsyncFetch, HTTPException
import random
import time
import binascii
from easing import easeInCubic
import machine

FADE_DURATION = 2000
UPDATE_INTERVAL = 10
RANDOMNESS = 32

SHAPES_API_HOST = "api.dicebear.com"
SHAPES_API_PATH = "/10.x/bottts-neutral/png?size=128&seed="
CACHE_FILE = "/lib/plugins/random_bots/random_bot.png"

UID = binascii.hexlify(machine.unique_id()).decode()

seed = random.getrandbits(RANDOMNESS)
img = image(128, 128)
old = image(128, 128)

try:
    old.load_into(CACHE_FILE)
except (OSError, ValueError):
    pass

api_data = AsyncFetch(SHAPES_API_HOST, debug=True)

api_data.fetch(f"{SHAPES_API_PATH}{UID}{seed}", file=CACHE_FILE, interval=UPDATE_INTERVAL)

fade_start = time.ticks_ms() - FADE_DURATION


@api_data.on_complete
def complete(_fetch):
    global fade_start

    # start the load for the NEXT image
    seed = random.getrandbits(RANDOMNESS)
    api_data.fetch(f"{SHAPES_API_PATH}{UID}{seed}", file=CACHE_FILE)

    # Load in the image we just downloaded.
    old.blit(img, vec2(0, 0))
    img.load_into(CACHE_FILE)

    fade_start = time.ticks_ms()


@api_data.on_error
def error(fetch):
    print(fetch.http_status, fetch.http_response_headers)

    seed = random.getrandbits(RANDOMNESS)
    api_data.fetch(f"{SHAPES_API_PATH}{UID}{seed}", file=CACHE_FILE, interval=UPDATE_INTERVAL)


def update():
    t = min(1.0, time.ticks_diff(time.ticks_ms(), fade_start) / FADE_DURATION)
    t = easeInCubic(t)

    screen.alpha = 255
    screen.blit(old, vec2(0, 0))
    screen.alpha = int(t * 255)
    screen.blit(img, vec2(0, 0))

    try:
        api_data.update()
    except HTTPException as e:
        print("Exception was raised!")
        print(e.fetch.http_status)
