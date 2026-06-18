from fetch import AsyncFetch, HTTPException
import random

FILE_PATH = "/lib/plugins/random_triangles/random_triangle.png"

center_x, center_y = screen.width / 2, screen.height / 2

SHAPES_API_HOST = "api.dicebear.com"
SHAPES_API_PATH = "/10.x/triangles/png?size=128&seed="
update_interval = 10
seed = random.getrandbits(32)
img = None

api_data = AsyncFetch(SHAPES_API_HOST, debug=True)
api_data.fetch(f"{SHAPES_API_PATH}{seed}", file=FILE_PATH, interval=update_interval)


@api_data.on_complete
def complete(fetch):
    global seed, img

    seed = random.getrandbits(32)
    api_data.fetch(f"{SHAPES_API_PATH}{seed}", file=FILE_PATH)
    img = image.load(FILE_PATH)


@api_data.on_error
def error(fetch):
    print(fetch.http_status, fetch.http_response_headers)


def update():

    try:
        api_data.update()
    except HTTPException as e:
        print("Exception was raised!")
        print(e.fetch.http_status)
    if img:
        screen.blit(img, rect(0, 0, 128, 128))

# while True:
#     update()
#     display.update()
