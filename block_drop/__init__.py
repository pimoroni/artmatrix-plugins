import random
import time

from plugin_config import plugin_config

cfg = plugin_config("block_drop", {
    "theme": "rainbow",  # one of THEMES
    "speed": "normal",  # one of SPEEDS
    "skill": "average",  # one of SKILLS
})
theme = cfg["theme"]
speed = cfg["speed"]
skill = cfg["skill"]

# the well in cells across and down, then px per cell
COLUMNS = 14
ROWS = 14
CELL = 8
# the well sits inside a border one block thick round the panel's edge
WELL_LEFT = CELL
WELL_TOP = CELL

# the pieces as drawn in their first turn, # for a block
SHAPES = (
    ("####",),
    ("##",
     "##"),
    (".#.",
     "###"),
    (".##",
     "##."),
    ("##.",
     ".##"),
    ("#..",
     "###"),
    ("..#",
     "###"),
)
# each theme's background as rgb, then each piece's colour in the same order
# as SHAPES. a piece's colour is oklch lightness, chroma and hue, 0-255 each,
# with 256 hue counts to a turn
THEMES = {
    "rainbow": ((8, 8, 18), (
        (170, 255, 219), (170, 255, 0), (170, 255, 37), (170, 255, 146),
        (170, 255, 73), (170, 255, 110), (170, 255, 183))),
    "berry": ((12, 0, 24), (
        (200, 255, 246), (140, 255, 240), (185, 255, 232), (120, 255, 228),
        (205, 255, 214), (105, 255, 206), (140, 255, 195))),
    "ocean": ((0, 20, 26), (
        (110, 255, 115), (205, 210, 124), (145, 255, 138), (230, 160, 140),
        (195, 255, 168), (140, 255, 172), (95, 200, 178))),
    "mono": ((0, 0, 0), (
        (90, 0, 0), (118, 0, 0), (146, 0, 0), (174, 0, 0),
        (202, 0, 0), (230, 0, 0), (255, 0, 0))),
}
if theme not in THEMES:
    theme = "rainbow"
background, pieces = THEMES[theme]
BACKGROUND = color.rgb(*background)
# the border's blocks, the same in every theme
BORDER_GREY = color.rgb(100, 100, 110)

# how the player scores a spot. lines cleared count for it, and the stack's
# total height, holes and bumps count against it
LINES_WEIGHT = 0.76
HEIGHT_WEIGHT = 0.51
HOLES_WEIGHT = 0.36
BUMPS_WEIGHT = 0.18
# the most random score added to each spot at level 1 for each skill, and how
# much more each level adds. it's what makes the player slip up and the stack grow
SKILLS = {
    "beginner": 4.0,
    "average": 2.0,
    "expert": 0.5,
}
if skill not in SKILLS:
    skill = "average"
SLIP_START = SKILLS[skill]
SLIP_PER_LEVEL = 0.4

# each speed's times as a multiple of the normal ones below
SPEEDS = {
    "slow": 1.5,
    "normal": 1.0,
    "fast": 0.6,
}
if speed not in SPEEDS:
    speed = "normal"
pace = SPEEDS[speed]

# ms a new piece waits before it moves, then ms between each turn or slide,
# and ms a row once it's lined up and dropping
THINK = int(800 * pace)
MOVE = int(250 * pace)
DROP = int(80 * pace)
# ms a slide takes to ease into the next column, then it holds there for the
# rest of the MOVE
SLIDE = int(120 * pace)
SLIDE_EASE = tween(0.0, 1.0, easing=tween.CUBIC_OUT)
# ms a row at level 1, how much quicker each level is, and the quickest it gets
FIRST_FALL = int(1200 * pace)
SPEEDUP = 0.95
FASTEST_FALL = int(400 * pace)
# lines cleared to go up a level
LINES_PER_LEVEL = 10

# ms full rows take to fade away
CLEAR = 700
# when the game ends, ms the stack stays, then ms it takes to fade away
OVER_HOLD = 1500
OVER_FADE = 1500

# a block width by height px, with a light top left edge and a dark bottom right
def bevel(base, width, height):
    tile = image(width, height)
    tile.pen = base
    tile.clear()
    tile.pen = base.lighten(50)
    tile.hspan(0, 0, width)
    tile.vspan(0, 0, height)
    tile.pen = base.darken(60)
    tile.hspan(1, height - 1, width - 1)
    tile.vspan(width - 1, 1, height - 1)
    return tile


BLOCKS = [bevel(color.oklch(*piece).fit(), CELL, CELL) for piece in pieces]

# what's behind the well: the background and the ring of border blocks
BACKDROP = image(screen.width, screen.height)
BACKDROP.pen = BACKGROUND
BACKDROP.clear()
BORDER_BLOCK = bevel(BORDER_GREY, CELL, CELL)
WELL_RIGHT = WELL_LEFT + COLUMNS * CELL
WELL_BOTTOM = WELL_TOP + ROWS * CELL
for index in range(COLUMNS + 2):
    BACKDROP.blit(BORDER_BLOCK, index * CELL, 0)
    BACKDROP.blit(BORDER_BLOCK, index * CELL, WELL_BOTTOM)
for index in range(ROWS):
    BACKDROP.blit(BORDER_BLOCK, 0, WELL_TOP + index * CELL)
    BACKDROP.blit(BORDER_BLOCK, WELL_RIGHT, WELL_TOP + index * CELL)

# every piece's turns, worked out by turning its drawing a quarter at a time.
# a turn that looks the same as one already found is skipped, so the square
# has one turn and the long piece two.
#
# each turn is a tuple of
#   cells: (column, row) of each block, from the turn's top left
#   width: columns it spans
#   profile: (column, top row, bottom row) for each column it covers
#   row_counts: (row, blocks in that row) for each row it covers
TURNS = []
for drawing in SHAPES:
    cells = [(column, row) for row, line in enumerate(drawing)
             for column, mark in enumerate(line) if mark == "#"]
    turns = []
    seen = []
    for _ in range(4):
        cells = sorted(cells)
        if cells not in seen:
            seen.append(cells)
            width = max(column for column, _ in cells) + 1
            height = max(row for _, row in cells) + 1
            profile = []
            for column in range(width):
                rows = [row for cell_column, row in cells if cell_column == column]
                profile.append((column, min(rows), max(rows)))
            row_counts = [(row, sum(1 for _, cell_row in cells if cell_row == row))
                          for row in range(height)]
            turns.append((tuple(cells), width, profile, row_counts))
        # a quarter turn clockwise
        height = max(row for _, row in cells) + 1
        cells = [(height - 1 - row, column) for column, row in cells]
    TURNS.append(turns)

# one byte per cell, row by row from the top. 0 is empty, otherwise it's
# 1 + the piece that left it there
grid = bytearray(COLUMNS * ROWS)

# the stack, drawn again only when it changes
board = image(screen.width, screen.height)

# pieces are dealt from a shuffled bag of one of each, so no piece goes missing
# for long
bag = []


# whether the turn's cells sit inside the well at x, y without hitting the stack
def fits(cells, x, y):
    for column, row in cells:
        column += x
        row += y
        if column < 0 or column >= COLUMNS or row >= ROWS:
            return False
        if grid[row * COLUMNS + column]:
            return False
    return True


def draw_board():
    board.blit(BACKDROP, 0, 0)
    for index, cell in enumerate(grid):
        if cell:
            board.blit(BLOCKS[cell - 1], WELL_LEFT + index % COLUMNS * CELL, WELL_TOP + index // COLUMNS * CELL)


# brings in a piece from the bag at the top of the well and picks where it
# should go. if there's no room for it the game is over
def spawn(now):
    global phase, phase_started, shape, turn, piece_x, piece_y, slide_from, slide_started
    global target_turn, target_x, dropping, fall_time, fall_due, move_due
    if not bag:
        bag.extend(range(len(SHAPES)))
    shape = bag.pop(random.randrange(len(bag)))
    turn = 0
    cells, width, _, _ = TURNS[shape][turn]
    piece_x = (COLUMNS - width) // 2
    piece_y = 0
    slide_from = piece_x * CELL
    slide_started = now
    phase_started = now
    draw_board()
    if not fits(cells, piece_x, piece_y):
        phase = "over"
        return
    phase = "play"

    # the top filled row of each column (ROWS if it's empty), the blocks in
    # each row, and the empty cells with a block somewhere above them
    tops = [ROWS] * COLUMNS
    filled = bytearray(ROWS)
    holes = 0
    for row in range(ROWS):
        for column in range(COLUMNS):
            if grid[row * COLUMNS + column]:
                filled[row] += 1
                if tops[column] == ROWS:
                    tops[column] = row
            elif tops[column] < row:
                holes += 1

    # score every turn in every column it fits, dropped straight down
    level_slip = SLIP_START + SLIP_PER_LEVEL * (level - 1)
    best_score = None
    target_turn = 0
    target_x = piece_x
    for turn_index, (_, width, profile, row_counts) in enumerate(TURNS[shape]):
        for x in range(COLUMNS - width + 1):
            # the lowest row the turn's top can reach before a column hits the stack
            landing = min(tops[x + column] - 1 - bottom for column, _, bottom in profile)
            if landing < 0:
                continue
            new_tops = list(tops)
            new_holes = holes
            for column, top, bottom in profile:
                # cells left empty under the piece
                new_holes += tops[x + column] - (landing + bottom) - 1
                new_tops[x + column] = landing + top
            cleared = 0
            for row, count in row_counts:
                if filled[landing + row] + count == COLUMNS:
                    cleared += 1
            # a cleared line takes a block off every column
            height = sum(ROWS - top for top in new_tops) - cleared * COLUMNS
            bumps = sum(abs(new_tops[column] - new_tops[column + 1]) for column in range(COLUMNS - 1))
            score = (LINES_WEIGHT * cleared - HEIGHT_WEIGHT * height
                     - HOLES_WEIGHT * new_holes - BUMPS_WEIGHT * bumps
                     + random.uniform(0, level_slip))
            if best_score is None or score > best_score:
                best_score = score
                target_turn = turn_index
                target_x = x

    dropping = False
    fall_time = max(FASTEST_FALL, int(FIRST_FALL * SPEEDUP ** (level - 1)))
    fall_due = time.ticks_add(now, fall_time)
    move_due = time.ticks_add(now, THINK)


def new_game(now):
    global lines, level
    for index in range(len(grid)):
        grid[index] = 0
    lines = 0
    level = 1
    spawn(now)


new_game(time.ticks_ms())


def update():
    global phase, phase_started, turn, piece_x, piece_y, slide_from, slide_started
    global dropping, fall_time, fall_due, move_due, target_turn, target_x, full, lines, level
    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, phase_started)

    if phase == "play":
        cells, width, _, _ = TURNS[shape][turn]

        # one turn or slide toward the target. if the stack is in the way it
        # gives up and drops the piece where it is
        if time.ticks_diff(now, move_due) >= 0 and not dropping:
            move_due = time.ticks_add(move_due, MOVE)
            if turn != target_turn:
                next_turn = (turn + 1) % len(TURNS[shape])
                next_cells, next_width, _, _ = TURNS[shape][next_turn]
                # keep the piece's middle where it was
                next_x = piece_x + (width - next_width) // 2
                if fits(next_cells, next_x, piece_y):
                    turn = next_turn
                    piece_x = next_x
                    cells = next_cells
                    slide_from = piece_x * CELL
                else:
                    target_turn = turn
                    target_x = piece_x
            elif piece_x != target_x:
                step = 1 if target_x > piece_x else -1
                if fits(cells, piece_x + step, piece_y):
                    slide_from = piece_x * CELL
                    slide_started = now
                    piece_x += step
                else:
                    target_x = piece_x
            else:
                # the drop keeps the share of this row the piece still has to fall,
                # or it would jump back to the top of the row
                remaining = time.ticks_diff(fall_due, now) / fall_time
                dropping = True
                fall_time = DROP
                fall_due = time.ticks_add(now, int(DROP * remaining))

        # down a row each fall_time. a piece that can't go down any further
        # is locked into the stack
        while time.ticks_diff(now, fall_due) >= 0:
            if fits(cells, piece_x, piece_y + 1):
                piece_y += 1
                fall_due = time.ticks_add(fall_due, fall_time)
            else:
                for column, row in cells:
                    grid[(piece_y + row) * COLUMNS + piece_x + column] = shape + 1
                full = [row for row in range(ROWS) if all(grid[row * COLUMNS:(row + 1) * COLUMNS])]
                if full:
                    phase = "clear"
                    phase_started = now
                    draw_board()
                else:
                    spawn(now)
                break

    elif phase == "clear" and elapsed >= CLEAR:
        kept = bytearray()
        for row in range(ROWS):
            if row not in full:
                kept += grid[row * COLUMNS:(row + 1) * COLUMNS]
        grid[:] = bytearray(len(full) * COLUMNS) + kept
        lines += len(full)
        level = 1 + lines // LINES_PER_LEVEL
        spawn(now)

    elif phase == "over" and elapsed >= OVER_HOLD + OVER_FADE:
        new_game(now)

    screen.blit(board, 0, 0)

    if phase == "play":
        cells, _, _, _ = TURNS[shape][turn]
        # px across, easing from slide_from into the piece's column over SLIDE
        slide = SLIDE_EASE.at(time.ticks_diff(now, slide_started) / SLIDE)
        left = slide_from + (piece_x * CELL - slide_from) * slide
        # px down, gliding toward the next row if there's room for it
        top = piece_y * CELL
        if fits(cells, piece_x, piece_y + 1):
            fallen = 1 - time.ticks_diff(fall_due, now) / fall_time
            top += CELL * clamp(fallen, 0, 1)
        for column, row in cells:
            screen.blit(BLOCKS[shape], WELL_LEFT + left + column * CELL, WELL_TOP + top + row * CELL)

    else:
        # full rows or, once the game's over, the whole well fading to the background
        if phase == "clear":
            fade = time.ticks_diff(now, phase_started) / CLEAR
            rows = full
        else:
            fade = (time.ticks_diff(now, phase_started) - OVER_HOLD) / OVER_FADE
            rows = range(ROWS)
        screen.pen = BACKGROUND.with_alpha(int(255 * clamp(fade, 0, 1)))
        for row in rows:
            screen.rectangle(WELL_LEFT, WELL_TOP + row * CELL, COLUMNS * CELL, CELL)
