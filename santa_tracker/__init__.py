"""Santa Tracker: December at the North Pole, then Santa's flight round the world.

From the first of December the North Pole gets busy: Santa checks his list (twice),
the elves make toys, the reindeer practise flying and the sleigh is loaded, with a
count of the sleeps left. On Christmas Eve he takes off, and a globe turns to follow
him from stop to stop, with the presents delivered so far and how long until he
reaches your house. When he flies into your part of the world the globe zooms in to
a map of it, to follow him town by town, and zooms out again when he has gone. When
he reaches you he's down your chimney, and then it's Christmas morning. The rest of the year the North Pole is quiet, counting sleeps.

The pictures are little films made in Blender (tools/ has all of it), kept in clips/
as JPEG frames. The route is Google's Santa Tracker's, cut down by tools/route.py:
see route.txt's licence in the README. Your house is wherever the settings page
says, or else where the Weather plugin's location is. Nothing is fetched: the
board's clock and time zone are all it needs.

Two ways to try it before Christmas, both on the settings page: show "demo" plays
the whole story in a few minutes, and show "pretend" starts the clock at any date
and time you like, running at life's speed or faster. Either way a small "test" in
the corner says the date on screen isn't the real one.
"""
import math
import struct
import time

import timezones
from plugin_config import plugin_config

HERE = "/lib/plugins/santa_tracker"

# These values are exposed to the web interface
cfg = plugin_config("santa_tracker", {
    "lat": None,  # blank uses the weather plugin's location
    "lng": None,
    "names": "",  # who to find on the nice list, separated by commas
    "units": "auto",  # how far away he is: miles, km, or auto to go by the board's time zone
    "show": "live",  # live, demo to play the whole story, or pretend to start at `pretend`
    "pretend": "",  # the local date and time pretend starts at, as 2026-12-24T09:55
    "speed": 1,  # how many times faster than life pretend runs: one of SPEEDS
})
lat = cfg["lat"]
lng = cfg["lng"]
names = cfg["names"] if isinstance(cfg["names"], str) else ""
# miles where the roads are in miles: the uk, and the united states' zones
MILES_ZONES = ("uk", "american_samoa", "hawaii", "alaska", "pacific", "arizona", "mountain", "central", "eastern")
units = cfg["units"] if cfg["units"] in ("miles", "km") else "auto"
unit_setting = units
if units == "auto":
    try:
        units = "miles" if timezones.zone()[0] in MILES_ZONES else "km"
    except (ValueError, AttributeError):
        units = "km"
show = cfg["show"] if cfg["show"] in ("live", "demo", "pretend") else "live"
pretend = cfg["pretend"] if isinstance(cfg["pretend"], str) else ""
# life's speed, a minute a second, ten minutes a second
SPEEDS = (1, 60, 600)
speed = cfg["speed"] if cfg["speed"] in SPEEDS else 1


def read_location(saved):
    # lat and lng as floats, or None if either is missing or isn't a number
    try:
        return float(saved["lat"]), float(saved["lng"])
    except (TypeError, ValueError):
        return None


# our own setting, or else one of the weather plugins', so a board that already
# shows the weather needn't be told where it is twice
location = (read_location(cfg) or read_location(plugin_config("weather", {"lat": None, "lng": None}))
            or read_location(plugin_config("weather_scenes", {"lat": None, "lng": None})))

# up to this many names off the settings page, each cut to what fits on a line
MOST_NAMES = 8
LONGEST_NAME = 12
nice = [name.strip()[:LONGEST_NAME] for name in names.replace(";", ",").split(",") if name.strip()][:MOST_NAMES]

# ---- the route ------------------------------------------------------------------

# a record a stop: latitude and longitude in hundredths of a degree, seconds after
# take-off that he arrives, thousands of presents delivered by the time he leaves,
# and 1 if it's a major city, which gets a present left on it on the globe
RECORD = "<hhIIH"
RECORD_BYTES = 14
# he stays this long at each stop
STOP = 60
# take-off, in utc, on christmas eve
TAKEOFF_HOUR = 10

with open(HERE + "/route.bin", "rb") as file:
    route = file.read()
with open(HERE + "/route.txt") as file:
    places = file.read().split("\n")
STOPS = len(route) // RECORD_BYTES
# the last stop is the landing, back at the north pole
FLIGHT = struct.unpack_from(RECORD, route, (STOPS - 1) * RECORD_BYTES)[2]


def stop(index):
    """A stop's latitude, longitude, arrival and presents."""
    a, b, arrive, presents, _ = struct.unpack_from(RECORD, route, index * RECORD_BYTES)
    return a / 100, b / 100, arrive, presents


def is_major(index):
    return route[index * RECORD_BYTES + 12] == 1


def nearest_stop(where):
    """The stop closest to a place: where Santa is when he does your house."""
    a = math.radians(where[0])
    best, best_far = None, 9
    for index in range(1, STOPS - 1):
        b, lon, _, _ = stop(index)
        b = math.radians(b)
        d = math.radians(lon - where[1])
        far = math.acos(max(min(math.sin(a) * math.sin(b) + math.cos(a) * math.cos(b) * math.cos(d), 1), -1))
        if far < best_far:
            best, best_far = index, far
    return best


home_stop = nearest_stop(location) if location else None
# seconds after take-off that he reaches your house
home_after = stop(home_stop)[2] if home_stop else None

def whereabouts(since):
    """Where Santa is `since` seconds after take-off: latitude, longitude, the stop he
    is at or heading for, whether he's there now, and the presents delivered."""
    since = min(max(since, 0), FLIGHT)
    # the last stop he has reached, found by halving
    reached, beyond = 0, STOPS
    while beyond - reached > 1:
        middle = (reached + beyond) // 2
        if struct.unpack_from("<I", route, middle * RECORD_BYTES + 4)[0] <= since:
            reached = middle
        else:
            beyond = middle
    a, b, arrive, presents = stop(reached)
    if reached == STOPS - 1:
        return a, b, reached, True, presents
    before = stop(reached - 1)[3] if reached else 0
    left = arrive + (STOP if reached else 0)
    if since < left:
        # on the roofs: the presents go down the chimneys while he's here
        return a, b, reached, True, before + (presents - before) * int(since - arrive) // STOP
    a2, b2, arrive2, _ = stop(reached + 1)
    along = (since - left) / max(arrive2 - left, 1)
    # the short way round, over the date line if need be
    turn = (b2 - b + 540) % 360 - 180
    return a + (a2 - a) * along, (b + turn * along + 540) % 360 - 180, reached + 1, False, presents


# ---- the clock --------------------------------------------------------------------

# the board's clock is utc, set over the network, and reads 2021 until it is
CLOCK_SET = time.mktime((2025, 1, 1, 0, 0, 0, 0, 0))
DAY = 86400
# how long the take-off film plays before the globe takes over, and how long he
# spends at your house
TAKEOFF_SECONDS = 20
VISIT_SECONDS = 14

started = time.ticks_ms()


def takeoff_of(year):
    return time.mktime((year, 12, 24, TAKEOFF_HOUR, 0, 0, 0, 0))


def offset(now):
    # seconds the local time is ahead of utc
    return timezones.utc_offset(int(now)) * 60


def local_noon(year, month, day):
    # utc for midday local on a date. the offset is taken on the day itself
    noon = time.mktime((year, month, day, 12, 0, 0, 0, 0))
    return noon - offset(noon)


def demo_script():
    """The story in a few minutes: (seconds it's shown for, the time it starts at, how
    many times faster than life it runs) for each part."""
    year = time.gmtime(time.time())[0] if time.time() > CLOCK_SET else 2026
    go = takeoff_of(year)
    parts = [(8, local_noon(year, 11, 30), 1), (9, local_noon(year, 12, 1), 1), (9, local_noon(year, 12, 6), 1),
             (9, local_noon(year, 12, 12), 1), (9, local_noon(year, 12, 20), 1), (7, go - 7, 1), (6, go, 1)]
    fast = 900
    if home_after:
        near = home_after - 640
        gone = home_after + VISIT_SECONDS + 300
        # his time near the house at 30 times life: the way in, the visit, the way out
        parts += [((near - TAKEOFF_SECONDS) / fast, go + TAKEOFF_SECONDS, fast), (640 / 30, go + near, 30),
                  (VISIT_SECONDS, go + home_after, 1), (10, go + home_after + VISIT_SECONDS, 30),
                  ((FLIGHT - gone) / fast, go + gone, fast)]
    else:
        parts += [((FLIGHT - TAKEOFF_SECONDS) / fast, go + TAKEOFF_SECONDS, fast)]
    parts += [(9, go + FLIGHT + 60, 1), (7, local_noon(year, 12, 27), 1)]
    return parts


def pretend_start(text):
    """Utc for a local date and time written as 2026-12-24T09:55, or None if it isn't one."""
    try:
        day, _, clock_time = text.partition("T")
        year, month, date = [int(part) for part in day.split("-")]
        hour, minute = [int(part) for part in clock_time.split(":")[:2]]
        if not (2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= date <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        local = time.mktime((year, month, date, hour, minute, 0, 0, 0))
        return local - offset(local)
    except (ValueError, TypeError, OverflowError):
        return None


script = demo_script() if show == "demo" else None
script_seconds = sum(part[0] for part in script) if script else 0
pretend_from = pretend_start(pretend) if show == "pretend" else None
# when he reaches the house in the pretend year, if that's still to come, and the
# fastest time runs while he's there
VISIT_SPEED = 30
# the slow spell: from LAST_SECONDS before he reaches the house, which takes in his
# last stops, to the end of his visit
LAST_SECONDS = 640
AWAY_SECONDS = 260
# the pretend clock's spells: (until this moment, at this many times life). his way
# in and out at no more than VISIT_SPEED, and the visit itself as it happens
spells = ()
if pretend_from is not None and home_after is not None:
    _home = takeoff_of(time.gmtime(pretend_from)[0]) + home_after
    _slow = min(speed, VISIT_SPEED)
    spells = ((_home - LAST_SECONDS, speed), (_home, _slow), (_home + VISIT_SECONDS, 1),
              (_home + VISIT_SECONDS + AWAY_SECONDS, _slow))
# the date on screen isn't the real one: a small "test" in the corner says so
testing = script is not None or pretend_from is not None


def local_text(when):
    # a utc time as the local date and time the settings page's box takes
    year, month, day, hour, minute = time.gmtime(when + offset(when))[:5]
    return f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"


# for the settings page's buttons: the christmas coming, and when he reaches the house
_now = time.time() if time.time() > CLOCK_SET else time.mktime((2026, 12, 1, 0, 0, 0, 0, 0))
_local = time.gmtime(_now + offset(_now))
test_year = _local[0] if (_local[1], _local[2]) <= (12, 26) else _local[0] + 1
takeoff_local = local_text(takeoff_of(test_year))
landing_local = local_text(takeoff_of(test_year) + FLIGHT)
visit_local = local_text(takeoff_of(test_year) + home_after) if home_after is not None else ""
visit_place = places[home_stop].split(", ")[0] if home_stop else ""


def clock():
    """The time now, in utc: the board's own, the demo's, or the pretend one. Always a
    whole number: the board's fractions hold only seven digits or so, and a time like
    this is nine, so as a fraction it would go in jumps of a minute."""
    if pretend_from is not None:
        run = time.ticks_diff(time.ticks_ms(), started) / 1000
        # his time near your house is worth watching: fast time slows down for it,
        # then picks up again
        now = int(pretend_from)
        for until, rate in spells:
            if until <= now:
                continue
            if run * rate < until - now:
                return now + int(run * rate)
            run -= (until - now) / rate
            now = int(until)
        return now + int(run * speed)
    if not script:
        return time.time()
    at = (time.ticks_diff(time.ticks_ms(), started) / 1000) % script_seconds
    for seconds, begins, rate in script:
        if at < seconds:
            return int(begins) + int(at * rate)
        at -= seconds
    return int(script[-1][1])


# ---- what to show -----------------------------------------------------------------

# seconds a scene stays before the next, about: it runs a whole number of loops
SCENE_SECONDS = 8
# seconds each line of a scene's caption shows
CAPTION_SECONDS = 4
# on the night, the globe shows for this long, then the sleigh for this long
GLOBE_SECONDS = 16
SLEIGH_SECONDS = 4
# the days in december each part of the story starts on
WORKSHOP_FROM = 5
PRACTICE_FROM = 10
LOADING_FROM = 18


def how_long(seconds):
    seconds = int(max(seconds, 0))
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60} min"
    return f"{seconds} sec"


def sleeps_line(sleeps):
    return f"{sleeps} sleeps to go" if sleeps > 1 else "Santa comes tonight!"


def plan(now):
    """What the screen should be doing at `now`: a key that changes when the playlist
    does, the playlist as (clip, captions) pairs, the number for the corner (or None),
    and seconds since take-off if he's flying."""
    # whole seconds: the board's calendar won't take a part of one
    now = int(now)
    local = time.gmtime(now + offset(now))
    year, month, day = local[0], local[1], local[2]
    go = takeoff_of(year)
    since = now - go
    # nights from today to christmas morning, this year's or next
    christmas = year if (month, day) <= (12, 25) else year + 1
    today = time.mktime((year, month, day, 0, 0, 0, 0, 0))
    sleeps = round((time.mktime((christmas, 12, 25, 0, 0, 0, 0, 0)) - today) / DAY)

    if 0 <= since < FLIGHT:
        if since < TAKEOFF_SECONDS:
            return "takeoff", [("takeoff", ("He's off!", "Go, Rudolph, go!"))], None, since
        if home_after is not None and home_after <= since < home_after + VISIT_SECONDS:
            return "visit", [("drop", ("Shh! Santa's here!", "Presents for you!"))], None, since
        return "flight", None, None, since

    if month == 12 and day <= 25 and since >= FLIGHT:
        lines = ("Santa's been!", "Merry Christmas!")
        return "morning", [("morning", lines), ("pole", ("Santa's home again", "and fast asleep"))], None, None

    if month == 12 and day <= 24:
        count = sleeps_line(sleeps)
        scenes = []
        if day == 24:
            wait = f"Take-off in {how_long(-since)}"
            scenes.append(("loading", ("Nearly ready to go!", wait)))
            scenes.append(("practice", ("One last practice", wait)))
        if day >= LOADING_FROM and day < 24:
            scenes.append(("loading", ("Loading the sleigh", count)))
        if day >= PRACTICE_FROM and day < 24:
            scenes.append(("practice", ("Flying practice!", count)))
        if day >= WORKSHOP_FROM:
            scenes.append(("workshop", ("The elves are busy", count)))
        checking = ["Checking the list...", "...checking it twice"]
        if nice:
            # a name a day, and everyone gets their turn through the month
            checking.append(nice[day % len(nice)] + ": NICE!")
        scenes.append(("checking", checking + [count]))
        scenes.append(("pole", ("The North Pole", count)))
        return f"advent{day}", scenes, sleeps, None

    if month == 12:
        return "rest", [("pole", ("Santa's having a rest", f"{sleeps} sleeps to go"))], None, None
    lines = ["All quiet up north", f"{sleeps} sleeps to go"]
    if month == 11:
        lines.insert(1, "Workshop opens 1 Dec")
    return "away", [("pole", lines)], None, None


# ---- the films --------------------------------------------------------------------

# no frame is bigger than this: tools/pack.py says how big the biggest is
BIGGEST = 12 * 1024
frame = bytearray(BIGGEST)
frame_view = memoryview(frame)


class Clip:
    """One of the films in clips/: any of its frames can be put on the screen."""

    def __init__(self, name):
        self.name = name
        self.file = open(f"{HERE}/clips/{name}.clip", "rb")
        magic, fps, self.frames = struct.unpack("<4sHH", self.file.read(8))
        self.fps = fps / 100
        self.starts = struct.unpack(f"<{self.frames + 1}I", self.file.read(4 * (self.frames + 1)))
        self.seconds = self.frames / self.fps

    def draw(self, index, onto=None):
        start = self.starts[index]
        size = self.starts[index + 1] - start
        self.file.seek(start)
        self.file.readinto(frame_view[:size])
        (onto or screen).load_into(frame_view[:size])

    def close(self):
        self.file.close()


# the film showing, and the globe, which stays open on the night
playing = None
globe = None


def film(name):
    global playing
    if playing is None or playing.name != name:
        if playing is not None:
            playing.close()
        playing = Clip(name)
    return playing


# ---- drawing ----------------------------------------------------------------------

FONT = font.load(HERE + "/santa.af")
WHITE = color.rgb(255, 255, 255)
CREAM = color.rgb(255, 240, 200)
GOLD = color.rgb(255, 205, 80)
SHADOW = color.rgb(4, 6, 24, 200)
BAR = color.rgb(6, 8, 30, 150)
RED = color.rgb(214, 30, 44)
GREEN = color.rgb(60, 220, 110)

# captions sit in a bar along the bottom, in letters this tall, or smaller to fit
CAPTION_SIZE = 12
SMALLEST = 8
BAR_TOP = 111


def fitted(text, size, room=124):
    """The biggest size up to `size` that `text` fits `room` at, and how wide it is then."""
    while True:
        width = screen.measure_text(text, size)[0]
        if width <= room or size <= SMALLEST:
            return size, width
        size -= 1


def write(text, y, size, pen, room=124, middle=64):
    """Text centred on `middle`, with a shadow so it reads over anything."""
    size, width = fitted(text, size, room)
    x = round(middle - width / 2)
    screen.pen = SHADOW
    screen.text(text, vec2(x + 1, y + 1), size)
    screen.pen = pen
    screen.text(text, vec2(x, y), size)


def caption(text, pen=WHITE):
    screen.pen = BAR
    screen.rectangle(0, BAR_TOP, 128, 128 - BAR_TOP)
    size, _ = fitted(text, CAPTION_SIZE)
    write(text, BAR_TOP + 1 + (CAPTION_SIZE - size) // 2, size, pen)


badge_ring = shape.circle(113, 14, 12.5)
badge_disc = shape.circle(113, 14, 11)


def badge(sleeps):
    """The sleeps left, on a bauble in the corner."""
    screen.pen = GOLD
    screen.shape(badge_ring)
    screen.pen = RED
    screen.shape(badge_disc)
    text = str(sleeps)
    size, width = fitted(text, 14, 18)
    screen.pen = WHITE
    screen.text(text, vec2(round(113 - width / 2), 14 - size // 2 - 1), size)


def test_mark():
    if testing:
        screen.pen = SHADOW
        screen.text("test", vec2(2, 1), 7)
        screen.pen = GOLD
        screen.text("test", vec2(1, 0), 7)


# ---- the globe --------------------------------------------------------------------

# the globe film has GLOBE_FRAMES views a turn apart, the first with longitude -180
# in the middle, seen from GLOBE_TILT degrees north. tools/pack.py puts the world at
# GLOBE_X, GLOBE_Y with GLOBE_RADIUS
GLOBE_FRAMES = 96
GLOBE_TILT = math.radians(20)
GLOBE_X, GLOBE_Y, GLOBE_RADIUS = 64, 61, 44
SIN_TILT, COS_TILT = math.sin(GLOBE_TILT), math.cos(GLOBE_TILT)
# the view looks this far ahead of him: he flies west, so he sits right of the middle
AHEAD = 14
# he flies this far above the ground, as a share of the world's radius
HEIGHT = 1.07
# the sparkles behind him: this many, this many seconds apart
TRAIL = 10
TRAIL_GAP = 100

# the sleigh's picture has SLEIGH_FRAMES steps of the gallop heading left, then the
# same heading right
sleigh = image.load(HERE + "/sleigh.png")
SLEIGH_FRAMES = 4
SLEIGH_WIDE = sleigh.width // (SLEIGH_FRAMES * 2)
SLEIGH_HIGH = sleigh.height
# the sleigh's runners, not its corner, go where he is. heading left the sleigh is
# the right-hand part of the picture
SLEIGH_AT = (SLEIGH_WIDE * 0.62, SLEIGH_HIGH * 0.8)
# a smaller one for the map of your area, where the towns are close together
small_sleigh = image.load(HERE + "/sleigh_small.png")
# he turns to face the next stop once it's this many pixels to one side: less, and
# he's flying up or down the map, and stays as he was
TURN = 2
heading_right = False

# every stop he has been to keeps a sparkle. these twinkle through these colours
TWINKLE = (color.rgb(255, 255, 255), color.rgb(255, 226, 120), color.rgb(255, 190, 70, 190), color.rgb(255, 170, 60, 110))
# where on the picture the stops he's been to are, for the view and the number of
# stops they were worked out for: only what's new is worked out again
visited = []
visited_view = -1
visited_upto = 0
# and the major cities among them, which get a present: where, and which wrapping
gifts = []
# wrapping paper and ribbon
WRAPPINGS = ((color.rgb(230, 40, 50), color.rgb(255, 215, 90)), (color.rgb(40, 190, 90), color.rgb(255, 255, 255)),
             (color.rgb(60, 130, 255), color.rgb(255, 215, 90)), (color.rgb(190, 90, 240), color.rgb(255, 255, 255)))
GIFT_EDGE = color.rgb(10, 12, 40, 170)


def draw_gift(x, y, wrapping):
    """A present 5 pixels wide and 6 high, bow and all, standing on x, y."""
    paper, ribbon = WRAPPINGS[wrapping]
    screen.pen = GIFT_EDGE
    screen.rectangle(x - 3, y - 5, 7, 6)
    screen.pen = paper
    screen.rectangle(x - 2, y - 4, 5, 4)
    screen.pen = ribbon
    screen.rectangle(x, y - 4, 1, 4)
    screen.rectangle(x - 1, y - 5, 3, 1)


def been_to(view, middle, upto):
    """Brings `visited` up to date: the stops up to `upto` that face us in this view."""
    global visited, gifts, visited_view, visited_upto
    if view != visited_view or upto < visited_upto:
        visited = []
        gifts = []
        visited_view = view
        visited_upto = 0
    for index in range(visited_upto + 1, upto + 1):
        a, b, _, _ = stop(index)
        x, y, facing = on_globe(a, b, middle)
        if facing:
            if is_major(index):
                gifts.append((round(x), round(y), index % len(WRAPPINGS)))
            else:
                visited.append((round(x), round(y)))
    visited_upto = upto

SPARKLES = [color.rgb(255, 225, 130, int(255 * (1 - i / TRAIL) ** 1.5)) for i in range(TRAIL)]
HOME = color.rgb(255, 70, 50)
HOME_GLOW = color.rgb(255, 230, 200, 120)


def on_globe(a, b, middle, height=1.0):
    """Where latitude a, longitude b is on the picture when `middle` is the longitude
    facing us, and whether it's on this side of the world."""
    a = math.radians(a)
    d = math.radians(b - middle)
    across = math.cos(a) * math.sin(d)
    up = math.sin(a)
    towards = math.cos(a) * math.cos(d)
    return (GLOBE_X + GLOBE_RADIUS * height * across,
            GLOBE_Y - GLOBE_RADIUS * height * (COS_TILT * up - SIN_TILT * towards),
            SIN_TILT * up + COS_TILT * towards > 0.05)


def presents_line(thousands):
    if thousands >= 1000000:
        return f"{thousands / 1000000:.2f} billion gifts"
    if thousands >= 1000:
        return f"{thousands // 1000} million gifts"
    return f"{thousands},000 gifts"


# where the sparkles are, and the time they were worked out for: they're only moved
# on when he has gone a quarter of the way to the next
trail = []
trail_at = -1e9


def twinkles(spots, ticks):
    """A sparkle on each of `spots`, twinkling in turn."""
    beat = ticks // 220
    for k in range(len(TWINKLE)):
        shade = (k + beat) % len(TWINKLE)
        screen.pen = TWINKLE[shade]
        for i in range(k, len(spots), len(TWINKLE)):
            x, y = spots[i]
            screen.rectangle(x, y, 1, 1)
        if shade == 1:
            # just past its brightest, a sparkle throws out four points
            screen.pen = TWINKLE[2]
            for i in range(k, len(spots), len(TWINKLE)):
                x, y = spots[i]
                screen.rectangle(x - 1, y, 3, 1)
                screen.rectangle(x, y - 1, 1, 3)
            screen.pen = TWINKLE[0]
            for i in range(k, len(spots), len(TWINKLE)):
                x, y = spots[i]
                screen.rectangle(x, y, 1, 1)


def draw_sleigh(x, y, ahead, there, ticks, picture=None):
    """The sleigh with its runners on x, y, facing the next stop, `ahead` pixels to one side."""
    global heading_right
    picture = picture or sleigh
    wide, high = picture.width // (SLEIGH_FRAMES * 2), picture.height
    if abs(ahead) >= TURN:
        heading_right = ahead > 0
    step = (ticks // 110) % SLEIGH_FRAMES + (SLEIGH_FRAMES if heading_right else 0)
    bob = 0 if there else round(math.sin(ticks / 300))
    left = x - wide * (0.38 if heading_right else 0.62)
    screen.blit(picture, rect(step * wide, 0, wide, high), rect(round(left), round(y - high * 0.8) + bob, wide, high))


# ---- close to home ----------------------------------------------------------------

# when he's in your part of the world the globe gives way to a map of it, and for
# his last few stops before your house to a closer one of just your area. both are
# drawn here from land.bin, which tools/land.py cuts into tiles, with your house in
# the middle. the first has REGION_SCALE pixels to a degree of latitude, so it's
# about 1800 km across. the second is as close as still shows his last stops
REGION_SCALE = 8
MAP_X, MAP_Y = 64, 64
LAND, WATER, BORDER = 0, 1, 2
SEA = color.rgb(8, 26, 92)
BORDER_PEN = color.rgb(190, 240, 200, 120)
# green, or whiter with snow if you live far to the north or south, as the globe is.
# one colour for the whole map: shaded by latitude, the tiles' edges would show
_snow = min(max((abs(location[0]) - 58) / 12, 0), 1) if location else 0
LAND_PEN = color.rgb(int(38 + 188 * _snow), int(150 + 86 * _snow), int(84 + 171 * _snow))
TOWN_PEN = color.rgb(20, 100, 60)
NAME_PEN = color.rgb(235, 250, 235, 215)
# he's close once he's this near the middle of the region's map, across and down in
# pixels, and stays close until he's this far out: the gap stops it flicking about
CLOSE_IN = (50, 38)
CLOSE_OUT = (68, 52)
# each step of the zoom takes this long, and the first magnifies the globe this much
ZOOM_MS = 900
ZOOM_GLOBE = 4
# close up, the sparkles behind him are this many seconds apart
CLOSE_GAP = 12
LOCAL_GAP = 3
KM_A_DEGREE = 111.2


class Map:
    """A map with your house in the middle, at `scale` pixels to a degree of latitude."""

    def __init__(self, scale, towns=()):
        self.scale = scale
        # near the poles a degree of longitude is very little ground: held at a quarter
        self.across = scale * max(math.cos(math.radians(location[0])), 0.25)
        self.picture = None
        self.ready = False
        # towns to mark on it: (latitude, longitude, name or None)
        self.towns = towns

    def at(self, a, b):
        return MAP_X + ((b - location[1] + 540) % 360 - 180) * self.across, MAP_Y - (a - location[0]) * self.scale

    def draw(self):
        """Draws the map, a tile at a time: each next() does one."""
        self.picture = picture = image(128, 128)
        picture.antialias = image.X2
        picture.pen = SEA
        picture.clear()
        yield
        with open(HERE + "/land.bin", "rb") as file:
            magic, tile, _ = struct.unpack("<4sHH", file.read(8))
            columns = 360 // tile
            half_lat = 64 / self.scale
            half_lon = 64 / self.across
            rows = range(int((max(location[0] - half_lat, -90) + 90) // tile), int((min(location[0] + half_lat, 89.99) + 90) // tile) + 1)
            across = range(math.floor((location[1] - half_lon + 180) / tile), math.floor((location[1] + half_lon + 180) / tile) + 1)
            # all the land, then the borders on it, then the lakes over both
            for wanted in (LAND, BORDER, WATER):
                for row in rows:
                    for column in across:
                        column %= columns
                        file.seek(8 + 8 * (row * columns + column))
                        start, size = struct.unpack("<II", file.read(8))
                        if not size:
                            continue
                        file.seek(start)
                        shapes = file.read(size)
                        west, south = column * tile - 180, row * tile - 90
                        at = 0
                        while at < size:
                            kind, count = struct.unpack_from("<BH", shapes, at)
                            if kind == wanted:
                                numbers = struct.unpack_from(f"<{count * 2}h", shapes, at + 3)
                                points = []
                                inside = False
                                for i in range(0, count * 2, 2):
                                    x, y = self.at(south + numbers[i + 1] / 1000, west + numbers[i] / 1000)
                                    inside = inside or (-64 < x < 192 and -64 < y < 192)
                                    points.append(vec2(x, y))
                                # a shape wholly off the picture is only drawn if it might cover it
                                if kind == BORDER:
                                    if inside:
                                        picture.pen = BORDER_PEN
                                        for i in range(count - 1):
                                            picture.line(points[i], points[i + 1])
                                elif inside or count >= 3:
                                    picture.pen = SEA if kind == WATER else LAND_PEN
                                    picture.shape(shape.custom(points))
                            at += 3 + count * 4
                        yield
        # the towns, then the names of those that have one, where there's room
        picture.font = FONT
        spots = []
        for a, b, name in self.towns:
            x, y = self.at(a, b)
            x, y = round(x), round(y)
            if 2 < x < 126 and 20 < y < 108:
                picture.pen = TOWN_PEN
                picture.rectangle(x - 1, y - 1, 3, 3)
                spots.append((x, y, name))
        # a name keeps clear of your house, the other names and the other towns
        taken = [(MAP_X - 16, MAP_Y - 16, MAP_X + 16, MAP_Y + 8)]
        for x, y, name in spots:
            if not name:
                continue
            width = picture.measure_text(name, 7)[0]
            for left in (x + 4, x - 4 - width):
                box = (left - 1, y - 5, left + width + 1, y + 4)
                if left < 1 or left + width > 126 or y - 5 < 20 or y + 4 > 109:
                    continue
                if any(box[0] < t[2] and box[2] > t[0] and box[1] < t[3] and box[3] > t[1] for t in taken):
                    continue
                if any(box[0] <= x2 <= box[2] and box[1] <= y2 <= box[3] for x2, y2, _ in spots if (x2, y2) != (x, y)):
                    continue
                taken.append(box)
                picture.pen = NAME_PEN
                picture.text(name, vec2(left, y - 5), 7)
                break
        yield
        self.ready = True


region = Map(REGION_SCALE) if location else None
# the closer map, once the towns near you are known
local = None
# the globe's picture, or the region's, while one zooms into the next
zoom_picture = None
# whatever is being got ready, a step a frame
getting_ready = None
# the route's stops on the region's map: which stop, where, and whether it's a major city
region_stops = []

# his stops near your house: real towns, each closer than the last, then your house,
# then a few more on his way out. they come from towns.bin, which tools/towns.py packs
# from GeoNames. the route itself has him fly straight in and out, so near you he
# takes his time: this tour starts before the route would have him here and ends
# after it has him gone, and then he flies fast to where the route says he should
# be, so nothing jumps.
# up to LAST_STOPS towns on the way in and AWAY_STOPS on the way out, from the NEAREST
# towns within REACH_KM. each takes LEG seconds: FLY of them flying there, the rest
# delivering. HOP seconds from the last to your house, CATCH_UP to rejoin the route
LAST_STOPS = 12
AWAY_STOPS = 4
NEAREST = 48
REACH_KM = 130
LEG = 50
FLY = 34
HOP = 20
CATCH_UP = 50
# (latitude, longitude, name, km from your house): furthest first on the way in,
# nearest first on the way out
last_stops = []
away_stops = []
# seconds after take-off that he starts on them, where he comes in from, and when
# he sets off again after his visit
last_from = None
last_entry = None
away_from = None
away_until = None


def find_last_stops():
    """Reads the towns near your house and picks his last stops. A generator, as draw() is."""
    global last_stops, last_from, last_entry, local, away_stops, away_from, away_until
    found = []
    with open(HERE + "/towns.bin", "rb") as file:
        magic, tile, _ = struct.unpack("<4sHH", file.read(8))
        columns = 360 // tile
        reach_lat = REACH_KM / KM_A_DEGREE
        reach_lon = reach_lat / max(math.cos(math.radians(location[0])), 0.25)
        squash = math.cos(math.radians(location[0]))
        rows = range(int((max(location[0] - reach_lat, -90) + 90) // tile), int((min(location[0] + reach_lat, 89.99) + 90) // tile) + 1)
        across = range(math.floor((location[1] - reach_lon + 180) / tile), math.floor((location[1] + reach_lon + 180) / tile) + 1)
        for row in rows:
            for column in across:
                column %= columns
                file.seek(8 + 8 * (row * columns + column))
                start, size = struct.unpack("<II", file.read(8))
                file.seek(start)
                towns = file.read(size)
                west, south = column * tile - 180, row * tile - 90
                at = 0
                while at < size:
                    east, north, people, letters = struct.unpack_from("<hhHB", towns, at)
                    a, b = south + north / 1000, west + east / 1000
                    over = ((b - location[1] + 540) % 360 - 180) * squash * KM_A_DEGREE
                    up = (a - location[0]) * KM_A_DEGREE
                    km = math.sqrt(over * over + up * up)
                    if km <= REACH_KM:
                        found.append((km, people, a, b, str(towns[at + 7:at + 7 + letters], "ascii")))
                    at += 7 + letters
                yield
    found.sort()
    found = found[:NEAREST]
    if len(found) >= 3 and home_after is not None:
        # the towns in rings by distance, the biggest of each ring, outermost first
        rings = min(LAST_STOPS, len(found))
        chosen = []
        for ring in range(rings):
            group = found[ring * len(found) // rings:(ring + 1) * len(found) // rings]
            km, people, a, b, name = max(group, key=lambda town: town[1])
            chosen.append((a, b, name, km))
        chosen.reverse()
        last_stops = chosen
        # on his way out, towns he hasn't been to, further and further off
        named = {town[2] for town in chosen}
        spare = [town for town in found if town[4] not in named]
        leaving = min(AWAY_STOPS, len(spare))
        for ring in range(leaving):
            group = spare[ring * len(spare) // leaving:(ring + 1) * len(spare) // leaving]
            km, people, a, b, name = max(group, key=lambda town: town[1])
            away_stops.append((a, b, name, km))
        away_from = home_after + VISIT_SECONDS
        away_until = away_from + LEG * len(away_stops)
        last_from = home_after - HOP - LEG * len(chosen)
        # he comes in from wherever the route has him, from just off the map
        a, b = whereabouts(last_from)[:2]
        over = ((b - location[1] + 540) % 360 - 180) * squash
        up = a - location[0]
        far = math.sqrt(over * over + up * up) or 1
        edge = chosen[0][3] * 1.5 / KM_A_DEGREE
        last_entry = (location[0] + up / far * edge, location[1] + over / far * edge / max(squash, 0.25))
        # the closer map shows the furthest of them 46 pixels from your house
        reach = max(chosen[0][3], 12)
        marked = [(a, b, name) for a, b, name, _ in chosen]
        marked += [(a, b, name) for a, b, name, _ in away_stops]
        named.update(town[2] for town in away_stops)
        marked += [(a, b, None) for _, _, a, b, name in found if name not in named]
        local = Map(46 / (reach / KM_A_DEGREE), marked)
    yield


def km_from_home(a, b):
    over = ((b - location[1] + 540) % 360 - 180) * math.cos(math.radians(location[0])) * KM_A_DEGREE
    up = (a - location[0]) * KM_A_DEGREE
    return math.sqrt(over * over + up * up)


def along_stops(spent, stops, start, end):
    """Where he is `spent` seconds into a run of `stops`, from `start`, with `end` after
    the last: latitude, longitude, which stop he's at or heading for (len(stops) is
    the end), and whether he's there."""
    index = min(max(int(spent // LEG), 0), len(stops))
    before = start if index == 0 else stops[index - 1]
    if index == len(stops):
        after = end
        along = (spent - index * LEG) / HOP
    else:
        after = stops[index]
        along = (spent - index * LEG) / FLY
    along = min(max(along, 0), 1)
    there = along >= 1
    along = along * along * (3 - 2 * along)
    return before[0] + (after[0] - before[0]) * along, before[1] + (after[1] - before[1]) * along, index, there


def last_whereabouts(since):
    """On his way in: as along_stops, where the end is your house."""
    return along_stops(since - last_from, last_stops, last_entry, location)


def away_whereabouts(since):
    """On his way out: as along_stops. After the last town he stays there."""
    a, b, index, there = along_stops(since - away_from, away_stops, location, away_stops[-1] if away_stops else location)
    return a, b, index, there or index == len(away_stops)


def near_whereabouts(since):
    """Latitude and longitude at any moment of his time near your house."""
    if since < home_after:
        return last_whereabouts(max(since, last_from))[:2]
    if since < away_from:
        return location
    return away_whereabouts(since)[:2]


def caught_up(since, a, b):
    """After his last town near you he flies fast to where the route has him, a, b:
    where he is on the way, which is a, b itself once he's there."""
    part = (since - away_until) / CATCH_UP
    if not 0 <= part < 1:
        return a, b
    part = part * part * (3 - 2 * part)
    a2, b2 = away_stops[-1][:2] if away_stops else location
    return a2 + (a - a2) * part, b2 + ((b - b2 + 540) % 360 - 180) * part


def get_ready():
    """Everything the close-up views need, a step a frame, from the start of the flight."""
    global zoom_picture
    zoom_picture = image(128, 128)
    yield
    for _ in region.draw():
        yield
    for index in range(1, STOPS - 1):
        a, b, _, _ = stop(index)
        x, y = region.at(a, b)
        if -4 < x < 132 and -4 < y < 132:
            region_stops.append((index, round(x), round(y), is_major(index)))
    yield
    for _ in find_last_stops():
        yield
    if local is not None:
        for _ in local.draw():
            yield


# 0 is the globe, 1 the region's map, 2 the closer one, between is a zoom. and
# whether he counts as close to your part of the world
zoom = 0.0
close = False
zoom_ticks = 0
close_trail = []
close_trail_at = -1e9

ROOF = color.rgb(214, 30, 44)
ROOF_DONE = color.rgb(40, 190, 90)
WALL = color.rgb(255, 240, 200)
WINDOW = color.rgb(255, 190, 60)
WAITING = color.rgb(210, 225, 255, 150)
LIT = color.rgb(255, 215, 90)


def draw_house(x, y, done, ticks):
    """Your house, 9 pixels wide, its doorstep on x, y, in a light that beats."""
    beat = 0.5 + 0.5 * math.sin(ticks / 250)
    screen.pen = HOME_GLOW
    screen.circle(x, y - 3, 6 + round(beat * 2))
    screen.pen = GIFT_EDGE
    screen.rectangle(x - 4, y - 5, 9, 6)
    screen.pen = WALL
    screen.rectangle(x - 3, y - 4, 7, 5)
    screen.pen = ROOF_DONE if done else ROOF
    for i in range(4):
        screen.rectangle(x - 4 + i, y - 5 - i, 9 - 2 * i, 1)
    screen.pen = WINDOW
    screen.rectangle(x - 2, y - 3, 2, 2)
    screen.pen = ROOF
    screen.rectangle(x + 1, y - 2, 2, 3)


def sparkle_trail(points, chart, ticks):
    for i, (a, b) in enumerate(points):
        x, y = chart.at(a, b)
        if (i + ticks // 120) % 3:
            screen.pen = SPARKLES[i]
            screen.rectangle(round(x), round(y) - 3, 2, 2)


def draw_close(since, ticks, a, b, heading, there):
    """The map of your part of the world, with him on it."""
    global close_trail, close_trail_at
    screen.blit(region.picture, 0, 0)
    upto = heading if there else heading - 1
    done = [(x, y) for index, x, y, major in region_stops if index <= upto and not major]
    # the houses still waiting are pale dots
    screen.pen = WAITING
    for index, x, y, _ in region_stops:
        if index > upto:
            screen.rectangle(x, y, 2, 2)
    twinkles(done, ticks)
    for index, x, y, major in region_stops:
        if major and index <= upto:
            draw_gift(x, y, index % len(WRAPPINGS))
    visited_home = home_after is not None and since >= home_after
    draw_house(MAP_X, MAP_Y, visited_home, ticks)
    if visited_home:
        draw_gift(MAP_X + 8, MAP_Y, 0)

    if abs(since - close_trail_at) > CLOSE_GAP / 4:
        close_trail_at = since
        close_trail = [whereabouts(since - i * CLOSE_GAP)[:2] for i in range(1, TRAIL) if since - i * CLOSE_GAP >= 0]
    sparkle_trail(close_trail, region, ticks)

    x, y = region.at(a, b)
    a2, b2, _, _ = stop(min(heading + 1, STOPS - 1) if there else heading)
    draw_sleigh(x, y - 2, region.at(a2, b2)[0] - x, there, ticks)


def draw_local(since, ticks):
    """The map of just your area, with him going from town to town."""
    screen.blit(local.picture, 0, 0)
    leaving = since >= away_from
    if leaving:
        a, b, index, there = away_whereabouts(since)
        been = len(last_stops) + index + (1 if there and index < len(away_stops) else 0)
        towns = away_stops
    else:
        a, b, index, there = last_whereabouts(since)
        been = index + (1 if there and index < len(last_stops) else 0)
        towns = last_stops
    done = []
    for i, (a2, b2, _, _) in enumerate(last_stops + away_stops):
        x, y = local.at(a2, b2)
        x, y = round(x), round(y)
        if i < been:
            # he's been: the town lights up
            screen.pen = LIT
            screen.rectangle(x - 1, y - 1, 3, 3)
            done.append((x, y - 3))
        else:
            screen.pen = WAITING
            screen.rectangle(x - 1, y - 1, 3, 3)
    twinkles(done, ticks)
    draw_house(MAP_X, MAP_Y, leaving, ticks)
    if leaving:
        draw_gift(MAP_X + 8, MAP_Y, 0)
    points = [near_whereabouts(since - i * LOCAL_GAP) for i in range(1, TRAIL) if since - i * LOCAL_GAP >= last_from]
    for i, (a2, b2) in enumerate(points):
        x, y = local.at(a2, b2)
        if (i + ticks // 120) % 3:
            screen.pen = SPARKLES[i]
            screen.rectangle(round(x), round(y) - 1, 1, 1)
    x, y = local.at(a, b)
    # he faces the town he's flying to, or the one after the one he's at
    ahead = index + (1 if there else 0)
    ahead = towns[ahead] if ahead < len(towns) else (towns[-1] if leaving and towns else location)
    draw_sleigh(x, y, local.at(ahead[0], ahead[1])[0] - x, there, ticks, small_sleigh)


def draw_far(since, ticks, a, b, heading, there, view, middle):
    """The globe, with him on it."""
    global trail, trail_at
    globe.draw(view)

    # a sparkle on every stop he has made, twinkling in turn. the landing isn't one
    been_to(view, middle, min(heading if there else heading - 1, STOPS - 2))
    twinkles(visited, ticks)
    # and a present on each major city
    for x, y, wrapping in gifts:
        draw_gift(x, y, wrapping)

    # your house, a light that beats
    if location:
        x, y, facing = on_globe(location[0], location[1], middle)
        if facing:
            beat = 0.5 + 0.5 * math.sin(ticks / 250)
            screen.pen = HOME_GLOW
            screen.circle(round(x), round(y), 2 + round(beat * 1.5))
            screen.pen = GREEN if home_after is not None and since >= home_after else HOME
            screen.rectangle(round(x) - 1, round(y) - 1, 2, 2)

    # the way he came, in sparkles that fade and twinkle
    if abs(since - trail_at) > TRAIL_GAP / 4:
        trail_at = since
        trail = [whereabouts(since - i * TRAIL_GAP)[:2] for i in range(1, TRAIL) if since - i * TRAIL_GAP >= 0]
    for i, (a2, b2) in enumerate(trail):
        x, y, facing = on_globe(a2, b2, middle, HEIGHT)
        if facing and (i + ticks // 120) % 3:
            screen.pen = SPARKLES[i]
            screen.rectangle(round(x), round(y), 1, 1)

    x, y, _ = on_globe(a, b, middle, HEIGHT)
    # he faces the way he's going: the stop he's flying to, or the one after this
    a2, b2, _, _ = stop(min(heading + 1, STOPS - 1) if there else heading)
    draw_sleigh(x, y, on_globe(a2, b2, middle, HEIGHT)[0] - x, there, ticks)


def draw_zoom(view, middle, part):
    """From the globe to the region's map: the globe swells towards your house, and
    the map comes through."""
    e = part * part * (3 - 2 * part)
    globe.draw(view, zoom_picture)
    x, y, facing = on_globe(location[0], location[1], middle)
    if not facing:
        x, y = GLOBE_X, GLOBE_Y
    # your house slides to the middle as the globe grows round it
    grown = 1 + (ZOOM_GLOBE - 1) * e
    wide = 128 / grown
    left = min(max(x - (x + (MAP_X - x) * e) / grown, 0), 128 - wide)
    top = min(max(y - (y + (MAP_Y - y) * e) / grown, 0), 128 - wide)
    screen.blit(zoom_picture, rect(left, top, wide, wide), rect(0, 0, 128, 128))
    through = (e - 0.3) / 0.7
    if through > 0:
        screen.alpha = int(255 * through)
        screen.blit(region.picture, 0, 0)
        screen.alpha = 255


def draw_closer(part):
    """From the region's map to the closer one: both have your house in the middle, so
    the first just grows until it is the second."""
    e = part * part * (3 - 2 * part)
    wide = 128 / math.pow(local.scale / region.scale, e)
    screen.blit(region.picture, rect(MAP_X - wide / 2, MAP_Y - wide / 2, wide, wide), rect(0, 0, 128, 128))
    through = (e - 0.45) / 0.55
    if through > 0:
        screen.alpha = int(255 * through)
        screen.blit(local.picture, 0, 0)
        screen.alpha = 255


def distance_line(km):
    amount = km if units == "km" else km / 1.609344
    word = "km" if units == "km" else ("mile" if round(amount) == 1 else "miles")
    if amount < 0.5:
        return "Right outside!"
    return f"Just {round(amount)} {word} away!" if amount < 9.5 else f"{round(amount)} {word} away"


def draw_globe(since, ticks):
    global globe, getting_ready, zoom, close, zoom_ticks
    if globe is None:
        globe = Clip("globe")
        if location:
            getting_ready = get_ready()
    a, b, heading, there, presents = whereabouts(since)

    # the close-up maps are got ready a step a frame, in good time
    if getting_ready is not None:
        try:
            next(getting_ready)
        except StopIteration:
            getting_ready = None

    # near your house he's on his own tour, on the closer map: his last stops, then
    # after his visit a few on the way out. then he catches the route up
    near = local is not None and local.ready
    last = near and last_from <= since < home_after
    leaving = near and away_from <= since < away_until
    if near and away_until <= since:
        a, b = caught_up(since, a, b)
    # which view he's due: the closer map on his tour, the region's while he's in your
    # part of the world, or else the globe. the zoom moves a step towards it
    if region is not None and region.ready:
        x, y = region.at(a, b)
        reach = CLOSE_OUT if close else CLOSE_IN
        close = abs(x - MAP_X) < reach[0] and abs(y - MAP_Y) < reach[1]
    want = 2 if last or leaving else 1 if close else 0
    step = min(max(time.ticks_diff(ticks, zoom_ticks), 0), 200) / ZOOM_MS
    zoom_ticks = ticks
    zoom = min(zoom + step, want) if zoom < want else max(zoom - step, want)

    if zoom >= 2:
        draw_local(since, ticks)
    elif zoom > 1:
        draw_closer(zoom - 1)
    elif zoom == 1:
        draw_close(since, ticks, a, b, heading, there)
    else:
        view = round((b - AHEAD + 180) / 360 * GLOBE_FRAMES) % GLOBE_FRAMES
        middle = view * 360 / GLOBE_FRAMES - 180
        if zoom > 0:
            draw_zoom(view, middle, zoom)
        else:
            draw_far(since, ticks, a, b, heading, there, view, middle)

    if last:
        # his last stops: the town, and how far off he is now
        la, lb, index, at_town = last_whereabouts(since)
        if index < len(last_stops):
            write("Delivering in:" if at_town else "Next stop:", 0, 8, CREAM)
            write(last_stops[index][2], 7, 11, WHITE)
        else:
            write("Next stop:", 0, 8, CREAM)
            write("Your house!", 7, 11, GOLD)
        km = km_from_home(la, lb)
        lines = (distance_line(km), f"Santa in {how_long(home_after - since)}", distance_line(km), "Quick, into bed!")
        caption(lines[(ticks // 2500) % len(lines)], GOLD)
        return
    if leaving:
        la, lb, index, at_town = away_whereabouts(since)
        index = min(index, len(away_stops) - 1)
        write("Delivering in:" if at_town else "Next stop:", 0, 8, CREAM)
        write(away_stops[index][2], 7, 11, WHITE)
        lines = ("He's been to yours!", "Merry Christmas!")
        caption(lines[(ticks // 2500) % len(lines)], WHITE)
        return

    place = places[heading].split(", ")
    if heading == STOPS - 1:
        label = "Home at last:" if there else "Heading home:"
    else:
        label = "Delivering in:" if there else "Next stop:"
    write(label, 0, 8, CREAM)
    write(place[0], 7, 11, WHITE)

    # along the bottom: the country, the presents, and how long till your house
    lines = [presents_line(presents)]
    if len(place) > 1:
        lines.insert(0, place[1])
    pen = WHITE
    if home_after is None:
        lines.append("Tell me where you live!")
    elif since < home_after:
        wait = home_after - since
        if wait < 1800:
            lines = ["Quick, into bed!", f"Santa in {how_long(wait)}"]
            pen = GOLD
        else:
            lines.append(f"Your house: {how_long(wait)}")
            if wait < 3 * 3600:
                lines.append("Nearly bedtime!")
    else:
        lines.append("He's been to yours!")
    caption(lines[(ticks // (CAPTION_SECONDS * 1000)) % len(lines)], pen)


# his visit: the map of your area swoops in on your house, and there he is on the
# roof, dropping the presents down the chimney. then back out to the map
SWOOP = 0.9
SWOOP_GROWS = 9


def draw_visit(at):
    """`at` seconds into his visit, which lasts VISIT_SECONDS."""
    clip = film("drop")
    index = int(max(at - SWOOP / 2, 0) * clip.fps) % clip.frames
    part = min(at / SWOOP, (VISIT_SECONDS - at) / SWOOP)
    if part >= 1 or local is None or not local.ready:
        clip.draw(index)
    else:
        e = max(part, 0)
        e = e * e * (3 - 2 * e)
        wide = 128 / math.pow(SWOOP_GROWS, e)
        screen.blit(local.picture, rect(MAP_X - wide / 2, MAP_Y - 3 - wide / 2 + 3 * (1 - e), wide, wide), rect(0, 0, 128, 128))
        if e < 0.35:
            draw_house(MAP_X, MAP_Y, at > VISIT_SECONDS / 2, 0)
        through = (e - 0.35) / 0.65
        if through > 0:
            clip.draw(index, zoom_picture)
            screen.alpha = int(255 * through)
            screen.blit(zoom_picture, 0, 0)
            screen.alpha = 255
    caption("Shh! Santa's here!" if at < VISIT_SECONDS / 2 else "Presents for you!", GOLD)


# ---- the frame --------------------------------------------------------------------

# the playlist in hand: its key, when it started, and the scene of it that's showing
playlist_key = None
playlist_started = 0


def update():
    global playlist_key, playlist_started

    ticks = time.ticks_diff(time.ticks_ms(), started)
    now = clock()
    if not testing and now < CLOCK_SET:
        # no time yet, so no date: the north pole, till the network gives one
        clip = film("pole")
        clip.draw(int(ticks / 1000 * clip.fps) % clip.frames)
        caption("Finding the time...")
        return

    key, scenes, sleeps, since = plan(now)
    if key != playlist_key:
        playlist_key = key
        playlist_started = ticks
    at = (ticks - playlist_started) / 1000

    if key == "visit":
        draw_visit(at)
        test_mark()
        return

    if scenes is None:
        # the night itself: the globe, and now and then the sleigh going by
        spell = at % (GLOBE_SECONDS + SLEIGH_SECONDS)
        # no cutting away while a close-up is on, or during his last stops
        nearly = last_from is not None and last_from - 30 <= since < away_until + CATCH_UP
        if spell < GLOBE_SECONDS or zoom > 0 or nearly:
            draw_globe(since, ticks)
            test_mark()
            return
        clip = film("flying")
        clip.draw(int((spell - GLOBE_SECONDS) * clip.fps) % clip.frames)
        if home_after is not None and since < home_after:
            caption(f"Your house: {how_long(home_after - since)}")
        else:
            caption("Merry Christmas!")
        test_mark()
        return

    # each scene runs whole loops, for about SCENE_SECONDS
    lengths = []
    for name, _ in scenes:
        loop = film(name).seconds if len(scenes) == 1 else LOOPS.get(name, 4.0)
        lengths.append(loop * max(round(SCENE_SECONDS / loop), 1))
    at %= sum(lengths)
    showing = 0
    while at >= lengths[showing]:
        at -= lengths[showing]
        showing += 1
    name, lines = scenes[showing]
    clip = film(name)
    clip.draw(int(at * clip.fps) % clip.frames)
    caption(lines[int(at / CAPTION_SECONDS) % len(lines)])
    if sleeps is not None and sleeps > 0:
        badge(sleeps)
    test_mark()


# how long each film's loop is, so a playlist can be timed without opening them all
LOOPS = {"pole": 4.0, "checking": 4.0, "workshop": 4.0, "practice": 4.0, "loading": 4.0,
         "takeoff": 5.0, "flying": 4.0, "drop": 6.0, "morning": 4.0}

screen.font = FONT
screen.antialias = image.X4
