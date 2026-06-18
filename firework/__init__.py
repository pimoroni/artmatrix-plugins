import random
import time

bg = image.load("/lib/plugins/firework/assets/bg.png")
fg = image.load("/lib/plugins/firework/assets/fg.png")

screen.antialias = image.X2
screen.font = rom_font.sins

sparks = []

p = shape.circle(0, 0, 1)
q = shape.circle(0, 0, 0.75)

# These values are exposed to the web interface.
frequencies = (0, 1, 1)  # Tuple containing the relative proportions of sparks with no children, with one generation of children and with two generations of children
timing = 100  # How often a firework is launched, in the form of "1 in x chance every frame"
gravity = 5  # Gravity level. Must be int.
max_speed = 32  # Maximum speed of the fireworks.
show_fps = False  # Displays framerate in the top left corner of the screen.

@micropython.native
def create_spark():
    x = random.randint(3200, 9600)
    y = 12800
    rgb = random.randint(0, len(colours) - 1)
    new_tier = random.choice(tiers)
    dy = random.uniform(-(max_speed * 7.5), -(max_speed * 10))
    dx = random.uniform(-60, 60)
    life = random.randint(30, 50)
    children = 0
    if int(new_tier) > 0:
        children = int(random.randint(30, 40))
    sparks.append((int(x), int(y), int(rgb), int(new_tier), int(dy), int(dx), int(life), int(life), int(children), 1))


@micropython.viper
def update_spark(x: int, y: int, rgb: int, tier: int, dy: int, dx: int, fulllife: int, life: int, children: int, alive: int):
    x += dx
    y += dy
    dy += int(gravity)
    life -= 1
    if life <= 0:
        alive = 0
        if tier > 0:
            for _i in range(children):
                make_child(x, y, rgb, tier, dy, dx, fulllife, children)
    if alive:
        sparks.append((x, y, rgb, tier, dy, dx, fulllife, life, children, alive))


@micropython.viper
def make_child(x: int, y: int, rgb: int, tier: int, dy: int, dx: int, fulllife: int, children: int):
    dx >> 1
    dy >> 1
    dx += int(random.randint(-100, 100))
    dy += int(random.randint(-100, 100))
    new_tier = tier - 1
    new_life: int = fulllife - int(random.randint(0, fulllife))
    new_children = children // 10
    sparks.append((x, y, rgb, new_tier, dy, dx, fulllife, new_life, new_children, 1))


@micropython.viper
def draw_sparks():
    for spark in sparks:
        x, y, rgb, tier, dy, dx, fullife, life, children, alive = spark
        screen.pen = colours[rgb]
        transformation = mat3().translate(int(x) // 100, int(y) // 100)
        p.transform = transformation
        q.transform = transformation
        screen.shape(p)
        screen.pen = color.white
        screen.shape(q)


screen.pen = color.rgb(0, 0, 0)
screen.clear()

tier_zero, tier_one, tier_two = frequencies

tiers = []

for _i in range(tier_zero):
    tiers.append(0)

for _i in range(tier_one):
    tiers.append(1)

for _i in range(tier_two):
    tiers.append(2)

colours = [color.rgb(255, 0, 0), color.rgb(255, 255, 0), color.rgb(0, 255, 0), color.rgb(0, 255, 255), color.rgb(0, 0, 255), color.rgb(255, 0, 255), color.rgb(255, 255, 255)]


@micropython.viper
def process_fireworks():
    screen.alpha = 20
    screen.blit(bg, vec2(0, 0))
    screen.alpha = 255

    for _spark in sparks:
        this_spark = sparks.pop(0)
        x, y, rgb, tier, dy, dx, fulllife, life, children, alive = this_spark
        update_spark(int(x), int(y), int(rgb), int(tier), int(dy), int(dx), int(fulllife), int(life), int(children), int(alive))

    draw_sparks()

    screen.blit(fg, vec2(0, 0))

    display.update()

    if not random.randint(0, timing):
        create_spark()


last_ticks = time.ticks_ms()

def update():
    global last_ticks
    process_fireworks()

    if show_fps:
        now = time.ticks_ms()
        frametime = now - last_ticks
        last_ticks = now
        fps = 1000 / frametime

        screen.pen = color.rgb(0, 0, 0)
        screen.rectangle(0, 0, 45, 12)

        screen.font = rom_font.sins
        screen.pen = color.red
        screen.text(str(fps), 0, 0)
