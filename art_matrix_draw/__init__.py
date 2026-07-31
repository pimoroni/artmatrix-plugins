import ubinascii

cx = screen.width / 2
cy = screen.height / 2

screen.font = font.smart

# try to load the image
try:
    uploaded_image = image.load("/lib/plugins/art_matrix_draw/artwork.png")
except OSError:
    uploaded_image = None

try:
    with open("/lib/plugins/art_matrix_draw/config.html", "r", encoding="utf-8") as f:
        config_html = f.read()
except OSError:
    config_html = None


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


def process_config(form):
    # The png is sent as a base64 encoded string
    # we need to decode that and write it back out to a file.
    data = ubinascii.a2b_base64(form["art_data"])
    with open("/lib/plugins/art_matrix_draw/artwork.png", "wb") as file:
        file.write(data)

    # Once this step has complete, the main.py reloads the plugin
    # so the image gets loaded in at the top :)


def update():
    # clear the screen to make way for your work of art.
    screen.pen = color.rgb(0, 0, 0)
    screen.clear()

    # and finally we display it for the world to see.
    if uploaded_image:
        screen.blit(uploaded_image, rect(0, 0, uploaded_image.width, uploaded_image.height), rect(0, 0, screen.width, screen.height))
    else:
        # instruct the user to visit the web app to get their Picasso on
        screen.pen = color.red
        centre_text("Nothing to show :(", cy - 50)
        screen.pen = color.blue
        centre_text("visit", cy - 10, 1)
        screen.pen = color.white
        centre_text("artmatrix.local", cy + 5, 2)
        screen.pen = color.blue
        centre_text("to create your", cy + 40, 1)
        centre_text("work of art", cy + 50, 1)
