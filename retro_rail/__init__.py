import time

import fetch

from plugin_config import plugin_config

# a uk station's departure board, like the amber dot matrix ones on the
# concourse. it shows a page of trains at a time and the clock. the config
# page picks departures, arrivals, or both one after the other
#
# live times come from national rail's darwin, through the huxley 2 json
# proxy. that needs a free darwin token. it's the consumer key of a
# subscription to "Live Departure Board Web Service (LDBWS) - Public" on the
# rail data marketplace, https://raildata.org.uk
#
# the lettering is daniel hart's dot matrix typeface, under the sil open font
# license, https://github.com/DanielHartUK/Dot-Matrix-Typeface. its dots are
# in dotmatrix.bin
cfg = plugin_config("retro_rail", {
    "station": "SHF",  # the station's three letter crs code
    "token": "",  # a darwin token. without one it shows sample times
    "board": "departures",  # departures, arrivals or both
})
station = cfg["station"].upper()
token = cfg["token"]
# the boards shown, one after the other
boards = ("departures", "arrivals") if cfg["board"] == "both" else (cfg["board"],)

HERE = __file__.rsplit("/", 1)[0]

HOST = "huxley2.azurewebsites.net"
# trains asked for, then seconds between fetches and after a failed one
TRAINS = 10
REFRESH = 60
RETRY = 30

# lit dots, unlit dots on the strips under the text, and the gaps between strips
AMBER = (255, 222, 0)
STRIP = (36, 32, 4)
UNLIT = (4, 3, 0)

# px round the edge hidden by the frame
EDGE = 1

# px down from the top to the heading, the first train and the footer. LINE
# is px from one train to the next
HEADING_ROW = 1
FIRST_ROW = 16
FOOTER_ROW = 115
LINE = 11
TRAIN_ROWS = (FOOTER_ROW - FIRST_ROW) // LINE

# px from a row's top to its text. the text is TEXT_HEIGHT tall with
# descenders, and so are the strips. the heading's strip is taller, with the
# text in its middle
TEXT_TOP = 3
TEXT_HEIGHT = 9
HEADING_HEIGHT = 15
# dot rows drawn twice in the heading to stretch it, like the font's tall figures
HEADING_REPEAT = (3, 5)

# where destinations start and platforms end, px from the left
DESTINATION_X = 26
PLATFORM_RIGHT = 93
# "Plat" sits this far right of the platform numbers
PLAT_SHIFT = 7

# dotmatrix.bin holds three faces. each character from space to "~" is a
# record: its advance in px, then one byte per dot row
REGULAR, BOLD, TALL = 0, 1, 2
DOTS = open(HERE + "/dotmatrix.bin", "rb").read()
RECORD = 1 + TEXT_HEIGHT
CHARACTERS = 95
# drawn text is cached, up to this many
PICTURES = 64

# ms each page shows for
PAGE = 8000

# long lines scroll. px a second, ms pause before each pass, and px gap
# before the text comes round again
SCROLL = 24
PAUSE = 1500
GAP = 30

# sheffield's trains, shown when there's no token
SAMPLE = (
    # minutes from now, destination, via, platform, minutes late or -1 for cancelled
    (3, "Leeds", None, "1", 0), (6, "Manchester Piccadilly", "via Stockport", "5", 0),
    (9, "London St Pancras International", None, "2", 4), (13, "Doncaster", None, "3", 0),
    (17, "Nottingham", None, "8", 0), (21, "Lincoln", "via Retford", "4", 0),
    (26, "York", None, "6", -1), (32, "Birmingham New Street", None, "7", 0),
    (38, "Huddersfield", "via Penistone", "1", 0), (44, "Cleethorpes", None, "3", 0),
)

# and arriving, the same columns with where they're from
SAMPLE_ARRIVALS = (
    (2, "Leeds", None, "6", 0), (5, "London St Pancras International", None, "5", 0),
    (8, "Manchester Piccadilly", "via Stockport", "1", 3), (12, "Doncaster", None, "4", 0),
    (16, "Nottingham", None, "2", -1), (20, "Huddersfield", "via Penistone", "8", 0),
    (25, "Birmingham New Street", None, "7", 0), (31, "York", None, "3", 0),
    (37, "Cleethorpes", None, "1", 0), (43, "Lincoln", "via Retford", "4", 0),
)

# each board's trains, as (time, destination or origin, via, platform,
# expected, cancelled). made is when national rail made a board, in seconds
# since midnight, and made_at the tick it came in on. problem is why a board's
# live times aren't showing
trains = {board: [] for board in boards}
made = None
made_at = 0
problem = dict.fromkeys(boards, "")

fetcher = fetch.AsyncFetch(HOST) if token else None
fetching = False
due = time.ticks_ms()
# boards[fetch_index] is being fetched, or is fetched next
fetch_index = 0

# when each scrolling line started, keyed by (row, text), and the cached text
# images, keyed by (face, text, repeat)
scrolls = {}
pictures = {}


# seconds the uk is ahead of utc at when, in seconds since the epoch. bst runs
# from 01:00 utc on march's last sunday to october's
def uk_offset(when):
    year = time.gmtime(when)[0]

    def last_sunday(month):
        month_end = time.mktime((year, month, 31, 1, 0, 0, 0, 0))
        return month_end - (time.gmtime(month_end)[6] + 1) % 7 * 86400

    return 3600 if last_sunday(3) <= when < last_sunday(10) else 0


# seconds since midnight in the uk. from national rail's time once a board has
# come in, else the rtc
def seconds_now():
    if made is not None:
        return (made + time.ticks_diff(time.ticks_ms(), made_at) // 1000) % 86400
    now = time.time()
    return (now + uk_offset(now)) % 86400


def hhmm(seconds):
    return "%02d:%02d" % (seconds // 3600 % 24, seconds // 60 % 60)


# fills each board with the sample trains, timed from this minute
def sample():
    minute = seconds_now() // 60 * 60
    for board in boards:
        trains[board] = []
        for minutes, place, via, platform, late in (SAMPLE_ARRIVALS if board == "arrivals" else SAMPLE):
            if late < 0:
                expected = "Cancelled"
            elif late:
                expected = hhmm(minute + (minutes + late) * 60)
            else:
                expected = "On time"
            trains[board].append((hhmm(minute + minutes * 60), place, via, platform, expected, late < 0))


# takes in a huxley 2 departures or arrivals board
def show(board, fetched):
    global made, made_at
    arriving = board == "arrivals"
    trains[board] = []
    for train in fetched.get("trainServices") or ():
        places = train.get("origin" if arriving else "destination") or ()
        place = " & ".join(location.get("locationName", "") for location in places)
        via = " ".join(location.get("via") or "" for location in places).strip() or None
        cancelled = bool(train.get("isCancelled"))
        scheduled = train.get("sta" if arriving else "std", "")
        expected = "Cancelled" if cancelled else train.get("eta" if arriving else "etd") or ""
        trains[board].append((scheduled, place, via, train.get("platform") or "", expected, cancelled))

    where = fetched.get("locationName") or station
    if trains[board]:
        problem[board] = ""
    elif arriving:
        problem[board] = "No arrivals at %s" % where
    else:
        problem[board] = "No departures from %s" % where

    # generatedAt is iso 8601, so hh:mm:ss starts at character 11
    stamp = fetched.get("generatedAt") or ""
    if len(stamp) >= 19:
        made = int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19])
        made_at = time.ticks_ms()


# starts a fetch when one's due, and takes in the board when it's done
def poll(now):
    global fetching, due, fetch_index
    if fetcher is None:
        return
    board = boards[fetch_index]
    if not fetching:
        if time.ticks_diff(now, due) < 0:
            return
        fetcher.fetch("/%s/%s/%d?accessToken=%s" % (board, station, TRAINS, token))
        fetching = True
    try:
        if fetcher.update() == fetch.AsyncFetch.FETCHING:
            return
        fetching = False
        show(board, fetcher.to_json())
        # the next board straight away, then a wait once they're all in
        fetch_index = (fetch_index + 1) % len(boards)
        due = now if fetch_index else time.ticks_add(now, REFRESH * 1000)
    except (OSError, ValueError, fetch.HTTPException) as error:
        fetching = False
        fetcher.reset()
        due = time.ticks_add(now, RETRY * 1000)
        problem[board] = "Can't reach National Rail (%s)" % error


# where a character's record starts in DOTS. an advance of 0 means the font
# has no such character, and those show as "?"
def record(face, character):
    code = ord(character) - 32
    if not 0 <= code < CHARACTERS or not DOTS[(face * CHARACTERS + code) * RECORD]:
        code = ord("?") - 32
    return (face * CHARACTERS + code) * RECORD


# the text's width in px, counting the gap after its last letter
def measure(face, text):
    return sum(DOTS[record(face, character)] for character in text)


# the text as lit dots on a clear image, with the dot rows in repeat drawn
# twice. each is drawn once, then cached
def picture(face, text, repeat=()):
    key = (face, text, repeat)
    if key not in pictures:
        if len(pictures) >= PICTURES:
            pictures.clear()
        dot_rows = []
        for dot_row in range(TEXT_HEIGHT):
            dot_rows += [dot_row, dot_row] if dot_row in repeat else [dot_row]
        drawn = image(max(1, measure(face, text)), len(dot_rows))
        drawn.antialias = image.OFF
        drawn.pen = color.rgb(0, 0, 0, 0)
        drawn.clear()
        drawn.pen = color.rgb(*AMBER)
        x = 0
        for character in text:
            start = record(face, character)
            for y, dot_row in enumerate(dot_rows):
                bits = DOTS[start + 1 + dot_row]
                for dot in range(8):
                    if bits & (0x80 >> dot):
                        drawn.rectangle(x + dot, y, 1, 1)
            x += DOTS[start]
        pictures[key] = drawn
    return pictures[key]


def write(face, text, x, y, repeat=()):
    screen.blit(picture(face, text, repeat), x, y)


# the text with its right edge at x, not counting the gap after its last letter
def right(face, text, x, y):
    write(face, text, x - measure(face, text) + 1, y)


# the text from x in a box width px wide. it scrolls round if it doesn't fit
def scroll(text, x, y, width, now):
    length = measure(REGULAR, text)
    if length <= width:
        write(REGULAR, text, x, y)
        return
    key = (y, text)
    started = scrolls.setdefault(key, now)
    shift = max(0, time.ticks_diff(now, started) - PAUSE) * SCROLL // 1000
    if shift >= length + GAP:
        scrolls[key] = now
        shift = 0
    screen.clip = rect(x, y, width, TEXT_HEIGHT)
    write(REGULAR, text, x - shift, y)
    write(REGULAR, text, x - shift + length + GAP, y)
    screen.clip = rect(EDGE, EDGE, screen.width - 2 * EDGE, screen.height - 2 * EDGE)


# each board's trains split into pages that fit, one board after the other. a
# page is (board, rows, page number, pages on that board), and a row is a
# train or the via line under one
def pages():
    shown = []
    for board in boards:
        split, page = [], []
        for train in trains[board]:
            via = train[2]
            if len(page) + (2 if via else 1) > TRAIN_ROWS:
                split.append(page)
                page = []
            page.append(train)
            if via:
                page.append(via)
        # an empty board still gets a page, for its heading and problem
        if page or not split:
            split.append(page)
        for number, rows in enumerate(split):
            shown.append((board, rows, number + 1, len(split)))
    return shown


if not token:
    sample()
# the minute the sample times were made for
sampled = seconds_now() // 60


def update():
    global sampled
    now = time.ticks_ms()
    poll(now)
    if not token and seconds_now() // 60 != sampled:
        sampled = seconds_now() // 60
        sample()

    screen.antialias = image.OFF
    screen.clip = rect(0, 0, screen.width, screen.height)
    screen.pen = color.rgb(*UNLIT)
    screen.clear()
    screen.clip = rect(EDGE, EDGE, screen.width - 2 * EDGE, screen.height - 2 * EDGE)
    right_edge = screen.width - EDGE

    # the strips. one round the heading, one under each row's text, one for the footer
    screen.pen = color.rgb(*STRIP)
    heading_top = HEADING_ROW + TEXT_TOP - (HEADING_HEIGHT - TEXT_HEIGHT) // 2
    screen.rectangle(EDGE, heading_top, right_edge - EDGE, HEADING_HEIGHT)
    for y in [FIRST_ROW + row * LINE for row in range(TRAIN_ROWS)] + [FOOTER_ROW]:
        screen.rectangle(EDGE, y + TEXT_TOP, right_edge - EDGE, TEXT_HEIGHT)

    shown = pages()
    board, rows, page_number, page_count = shown[now // PAGE % len(shown)]

    # the heading in the middle of its strip. Plat and Expt sit on its
    # baseline, below the repeated rows
    top = heading_top + (HEADING_HEIGHT - TEXT_HEIGHT - len(HEADING_REPEAT)) // 2
    write(BOLD, "Arrivals" if board == "arrivals" else "Departures", EDGE, top, HEADING_REPEAT)
    top += len(HEADING_REPEAT)
    right(REGULAR, "Plat", PLATFORM_RIGHT + PLAT_SHIFT, top)
    right(REGULAR, "Expt", right_edge, top)

    y = FIRST_ROW
    for row in rows:
        top = y + TEXT_TOP
        # a via line is a plain string, a train is a tuple
        if isinstance(row, str):
            via = row[:1].upper() + row[1:]
            scroll(via, DESTINATION_X, top, right_edge - DESTINATION_X, now)
        else:
            departs, destination, _, platform, expected, cancelled = row
            write(REGULAR, departs, EDGE, top)
            # a cancelled train has no platform, so its destination runs up to "Cancelled"
            if cancelled:
                destination_end = right_edge - measure(REGULAR, expected) - 3
            else:
                # room for a two digit platform
                destination_end = PLATFORM_RIGHT - measure(REGULAR, "88") - 1
                right(REGULAR, platform, PLATFORM_RIGHT, top)
            right(REGULAR, expected, right_edge, top)
            scroll(destination, DESTINATION_X, top, destination_end - DESTINATION_X, now)
        y += LINE

    # the clock in tall figures, the footer's text on their baseline
    seconds = seconds_now()
    clock = "%02d:%02d:%02d" % (seconds // 3600, seconds // 60 % 60, seconds % 60)
    top = FOOTER_ROW + TEXT_TOP
    clock_width = measure(TALL, clock)
    right(TALL, clock, right_edge, top)
    if problem[board]:
        footer = problem[board]
    elif page_count > 1:
        footer = "Page %d of %d" % (page_number, page_count)
    else:
        footer = ""
    if footer:
        scroll(footer, EDGE, top + 2, right_edge - clock_width - 3 - EDGE, now)
