import ubinascii

from qr_screen import draw_qr_screen

# try to load the image
try:
    uploaded_image = image.load("/lib/plugins/art_matrix_draw/artwork.png")
except OSError:
    uploaded_image = None


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
        draw_qr_screen("Art Matrix Draw", "Nothing drawn yet", "art_matrix_draw")
