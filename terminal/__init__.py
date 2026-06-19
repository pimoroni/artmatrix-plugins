import random
import time

black = color.rgb(0, 0, 0)
background = color.rgb(0, 0, 0)
phosphor = color.rgb(246, 135, 4)
terminal_text = color.rgb(0, 128, 0)

class Terminal:
    lines = []
    max_lines = 25
    line_added_at = None
    lines_added = 0
    speed = 250

    def update():
        if time.ticks_ms() - Terminal.line_added_at > Terminal.speed:
            Terminal.add_line()

    def add_line():
        Terminal.lines.append(random.randint(20, 140))
        Terminal.line_added_at = time.ticks_ms()
        Terminal.lines_added += 1
        if len(Terminal.lines) > Terminal.max_lines:
            Terminal.lines = Terminal.lines[len(Terminal.lines) - Terminal.max_lines:]


# pre populate the terminal
for _ in range(35):
    Terminal.add_line()


# the terminal effect creates a rolling window of text that is infinitely
# populated with new lines
def draw_terminal():
    screen.pen = terminal_text

    # update the fake terminal
    Terminal.update()

    for i in range(25):
        # work out the position of screen that this line will be rendered
        y = 7 + i * 5
        yo = ((time.ticks_ms() - Terminal.line_added_at) / Terminal.speed) * 5
        y = int(y - yo)

        # force the random seed so that word widths will always be consistent for
        # each line...
        random.seed(i + Terminal.lines_added)
        cx = 0
        while cx < Terminal.lines[i]:
            # pick a random word width
            w = random.randint(3, 10)
            # draw the "greeked" word
            screen.rectangle(cx + 2, y, w, 2)
            # rect.transform = mat3().translate(cx + 5, y).scale(w, 2)
            # screen.shape(rect)
            # add a space
            cx += w + 2


def update():
    screen.pen = color.rgb(0, 0, 0)
    screen.clear()
    draw_terminal()
    display.update()
