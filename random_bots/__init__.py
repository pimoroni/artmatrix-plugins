from fetch import AsyncFetch, HTTPException
import random
import time
from easing import easeOutCubic

center_x, center_y = screen.width / 2, screen.height / 2

SHAPES_API_HOST = "api.dicebear.com"
SHAPES_API_PATH = "/10.x/bottts-neutral/png?size=128&seed="
update_interval = 5
seed = random.getrandbits(32)
img = [None, None]

current = 0
api_data = AsyncFetch(SHAPES_API_HOST, debug=True)

api_data.fetch(f"{SHAPES_API_PATH}{seed}", file=f"/lib/plugins/random_bots/random_bot_{current}.png", interval=update_interval)

fade_start = time.ticks_ms()
fade_duration = 2000


@api_data.on_complete
def complete(fetch):
    global seed, current, fade_start

    current = (current + 1) % 2

    # Load in the image we just downloaded.
    img[current] = image.load(f"/lib/plugins/random_bots/random_bot_{current}.png")

    # start the load for the NEXT image
    seed = random.getrandbits(32)
    next_download = (current + 1) % 2
    api_data.fetch(f"{SHAPES_API_PATH}{seed}", file=f"/lib/plugins/random_bots/random_bot_{next_download}.png")

    fade_start = time.ticks_ms()


@api_data.on_error
def error(fetch):
    print(fetch.http_status, fetch.http_response_headers)


def update():

    t = min(1.0, time.ticks_diff(time.ticks_ms(), fade_start) / fade_duration)
    t = easeOutCubic(t)

    try:
        api_data.update()
    except HTTPException as e:
        print("Exception was raised!")
        print(e.fetch.http_status)

    if img[current] and t < 1.0:
        img[current].alpha = int(t * 255)
        screen.blit(img[current], rect(0, 0, 128, 128))

    out = (current + 1) % 2
    if img[out]:
        img[out].alpha = int((1.0 - t) * 255)
        screen.blit(img[out], rect(0, 0, 128, 128))

    display.update()
