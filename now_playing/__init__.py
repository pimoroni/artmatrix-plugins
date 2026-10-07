import config
import gc
import json
import os
import time
from easing import easeInCubic
from scrolling import Scroll
from fetch import AsyncFetch, HTTPException

from plugin_config import plugin_config

cy = screen.height / 2
DATA_PATH = "/lib/plugins/now_playing"
API_HOST = "api.spotify.com"
API_PATH = "/v1/me/player/currently-playing"
API_UPDATE_TIME = 5
API_COVER_HOST = "i.scdn.co"
FADE_DURATION = 3000
MAX_COVERS = 100
TOKEN_KEYS = ("access_token", "refresh_token", "client_id")
SD_LOGO_PATH = "/assets/sd_card_error.png"


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
    tokens = {}
    settings = {}
    for key, value in form.items():
        if key in TOKEN_KEYS:
            tokens[key] = value
        else:
            settings[key] = value
    if tokens:
        with open(f"{DATA_PATH}/spotify_tokens.json", "w") as file:
            json.dump(tokens, file)
    if settings:
        with open(f"{DATA_PATH}/config.json", "w") as file:
            json.dump(settings, file)


class Settings:
    show_pause_screen = True
    album_art_dir = f"{DATA_PATH}/albums"
    show_title = True
    scroll_speed = 30
    client_id = ""


class Token:
    access = None
    refresh = None
    last_update = None
    refresh_time = 1800   # 30 minutes in seconds
    header = {"Content-Type": "application/x-www-form-urlencoded"}
    data = None
    HOST = "accounts.spotify.com"
    PATH = "/api/token"
    auth_header = {"Authorization": f"Bearer {access}"}


def quote(s):
    always_safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
    res = []
    for c in s:
        if c in always_safe:
            res.append(c)
            continue
        res.append("%%%x" % ord(c))
    return "".join(res)


def urlencode(query):
    if isinstance(query, dict):
        query = query.items()
    li = []
    for k, v in query:
        if not isinstance(v, list):
            v = [v]
        for value in v:
            k = quote(str(k))
            v = quote(str(value))
            li.append(k + "=" + v)
    return "&".join(li)


# Load settings
cfg = plugin_config("now_playing", {
    "show_pause_screen": True,
    "album_art_dir": Settings.album_art_dir,
    "show_track_title": True,
    "scroll_speed": 30,
})
Settings.show_pause_screen = cfg["show_pause_screen"]
Settings.album_art_dir = cfg["album_art_dir"]
Settings.show_title = cfg["show_track_title"]
Settings.scroll_speed = cfg["scroll_speed"]
tokens = None
try:
    with open(f"{DATA_PATH}/spotify_tokens.json", "r") as file:
        tokens = json.load(file)
except (OSError, ValueError):
    pass
if tokens and tokens.get("refresh_token"):
    Token.access = tokens.get("access_token")
    Token.refresh = tokens["refresh_token"]
    Settings.client_id = tokens.get("client_id", "")
    Token.data = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": Token.refresh,
        "client_id": Settings.client_id,
    })
    authenticated = True
    # Update the access token in the dict
    Token.auth_header["Authorization"] = f"Bearer {Token.access}"
else:
    # If there are no tokens, auth needs to be completed.
    authenticated = False
# check the path exists and creates it if not.
try:
    os.mkdir(Settings.album_art_dir)
except OSError:
    pass

# load the sd card icon, we might need it later...
try:
    sd_logo = image.load(SD_LOGO_PATH)
except OSError:
    sd_logo = None


class View:
    def __init__(self):
        self.view = image(128, 128)

    def render(self):
        pass

    def update(self):
        pass

    def reset(self):
        pass


class Track(View):
    def __init__(self):
        super().__init__()
        self.scroll_obj = None
        self.playing = False
        self.cover = None
        self.title = None
        self.artist = None
        self.file_name = None
        self.album_id = None

    def render(self):
        self.view.pen = color.black
        self.view.clear()
        self.view.pen = color.white
        if self.cover:
            self.view.blit(self.cover, rect(0, 0, self.cover.width, self.cover.height), rect(1, 1, 126, 126))
        if self.scroll_obj:
            self.scroll_obj.update()
            self.view.pen = color.rgb(0, 0, 0, 150)
            self.view.rectangle(0, 118, screen.width, 10)
            self.view.pen = color.white
            self.scroll_obj.render()
        return self.view


class NotPlayingView(View):
    def __init__(self):
        super().__init__()
        self.title = None
        self.artist = None
        self.cover = None
        self.last_view = None
        self.album_id = None

    def render(self):
        self.view.font = font.sins
        self.view.pen = color.black
        self.view.clear()
        # Check that there is a last view and cover.
        if self.last_view is not None:
            if tracks[self.last_view].cover:
                # display the cover of the paused track and blur is.
                self.view.blit(tracks[self.last_view].cover, rect(0, 0, tracks[self.last_view].cover.width, tracks[self.last_view].cover.height), rect(1, 1, 126, 126))
                self.view.blur(1)
        # display and centre the text on the X and Y
        t = "Stopped/Paused"
        tw, th = self.view.measure_text(t)
        tx = self.view.width / 2 - (tw / 2)
        ty = self.view.height / 2 - (th / 2)
        self.view.pen = color.rgb(0, 0, 0, 130)
        self.view.shape(shape.rectangle(0, ty, self.view.width, th))
        self.view.pen = color.white
        self.view.text(t, vec2(tx, ty))
        return self.view


tracks = (Track(), Track(), NotPlayingView())
current_view = 0
cover_slot = 0
storage_error = False
api_data = AsyncFetch(API_HOST, debug=True)
api_token_refresh = AsyncFetch(Token.HOST, debug=True)
api_cover_art = AsyncFetch(API_COVER_HOST, debug=True)


def load_track_art(track):
    global current_view, fade_start, storage_error
    art_path = f"{Settings.album_art_dir}/{tracks[track].file_name}"
    try:
        tracks[track].cover = image.load(art_path)
    except ValueError:
        # corrupt or part-downloaded, so drop it and let the next poll fetch it again
        os.remove(art_path)
        return
    storage_error = False
    current_view = track
    fade_start = time.ticks_ms()


@api_data.on_complete
def handle_complete(fetch):
    global current_view, cover_slot, storage_error
    # Check that the cover art fetch is not in progress.
    if api_cover_art.status is AsyncFetch.IDLE:
        try:
            # The data recieved, in JSON format
            received_data = fetch.to_json()
        except (OSError, ValueError):
            return
        # check to see if the currently playing is music. Not a podcast or audiobook.
        if received_data.get("currently_playing_type") == "track":
            try:
                # The next track to load into
                track_id = (current_view + 1) % 2
                tracks[track_id].title = received_data["item"]["name"]
                tracks[track_id].artist = received_data["item"]["artists"][0]["name"]
                tracks[track_id].album_id = received_data["item"]["album"]["id"]
                # If the track isn't playing, set the track accordingly and end here.
                tracks[track_id].playing = received_data["is_playing"]
                cover_url = received_data["item"]["album"]["images"][1]["url"]
            except (KeyError, IndexError):
                return
            if not tracks[track_id].playing and Settings.show_pause_screen:
                if tracks[2].last_view is None:
                    tracks[2].last_view = current_view
                current_view = 2
                return
            tracks[2].last_view = None
            if tracks[track_id].album_id != tracks[current_view].album_id or tracks[track_id].title != tracks[current_view].title or tracks[current_view].album_id is None:
                # start the cover art fetch
                try:
                    path = cover_url.split("/")
                    tracks[track_id].file_name = f"{path[4]}.jpg"
                    full_path = f"{Settings.album_art_dir}/{tracks[track_id].file_name}"
                    if tracks[track_id].file_name not in os.listdir(Settings.album_art_dir):
                        cover_slot = track_id
                        api_cover_art.fetch(f"{path[3]}/{path[4]}", file=full_path)
                    else:
                        load_track_art(track_id)
                except OSError as e:
                    storage_error = True
                    print(f"STORAGE ERROR (art dir unreachable): {e}")
                    return
                # Create the scroll object for the new track title
                if Settings.show_title:
                    tracks[track_id].scroll_obj = Scroll(f"{tracks[track_id].title} - {tracks[track_id].artist}", target=tracks[track_id].view, speed=Settings.scroll_speed, align="bottom")
        else:
            current_view = 2
        gc.collect()


@api_data.on_error
def json_error(fetch):
    print(fetch.http_status, bytes(fetch.body))


@api_cover_art.on_complete
def json_complete(_fetch):
    load_track_art(cover_slot)
    # keep the cache to MAX_COVERS, never the two covers on screen
    try:
        covers = os.listdir(Settings.album_art_dir)
        excess = len(covers) - MAX_COVERS
        keep = (tracks[0].file_name, tracks[1].file_name)
        for name in covers:
            if excess <= 0:
                break
            if name in keep:
                continue
            os.remove(f"{Settings.album_art_dir}/{name}")
            excess -= 1
    except OSError as e:
        print(f"PRUNE ERR: {e}")


@api_cover_art.on_error
def cover_error(fetch):
    print(fetch.http_status)
    # the error body was saved in place of the cover
    try:
        os.remove(fetch.destination)
    except OSError:
        pass
    return True


@api_token_refresh.on_complete
def token_complete(fetch):
    try:
        data = fetch.to_json()
        Token.access = data["access_token"]
    except (OSError, ValueError, KeyError):
        return
    Token.refresh = data.get("refresh_token", Token.refresh)
    Token.last_update = time.ticks_ms()
    with open(f"{DATA_PATH}/spotify_tokens.json", "w") as f:
        json.dump({"access_token": Token.access, "refresh_token": Token.refresh,
                   "client_id": Settings.client_id}, f)
    Token.data = urlencode({"grant_type": "refresh_token",
                            "refresh_token": Token.refresh,
                            "client_id": Settings.client_id})
    Token.auth_header["Authorization"] = f"Bearer {Token.access}"

    # put the new header into the AsyncFetch so it actually uses it.
    api_data._headers["Authorization"] = f"Bearer {Token.access}"  # noqa: SLF001
    # the interval resends the stored body, so give it the new refresh token
    api_token_refresh.fetch(Token.PATH, data=Token.data, headers=Token.header,
                            method="POST", interval=Token.refresh_time)


@api_token_refresh.on_error
def token_error(fetch):
    global authenticated
    print(fetch.http_status, bytes(fetch.body))
    # 400 is Spotify refusing the refresh token or client id, only re-authorising fixes that
    if fetch.http_status == 400:
        authenticated = False
    return True


# start the fetch, but only if the authentication process has completed.
if authenticated:
    api_token_refresh.fetch(Token.PATH, data=Token.data, headers=Token.header, method="POST", interval=Token.refresh_time)
    api_data.fetch(API_PATH, headers=Token.auth_header, interval=API_UPDATE_TIME)
fade_start = time.ticks_ms() - FADE_DURATION


def update():
    global current_view
    # clear the display
    screen.pen = color.rgb(0, 0, 0)
    screen.clear()
    if authenticated:
        try:
            try:
                api_token_refresh.update()
            except OSError as e:
                print(f"TOKEN ERR: {e}")
            try:
                api_cover_art.update()
            except OSError as e:
                print(f"COVER ART ERR: {e}")
                # a part-written cover would sit in the cache and never be fetched again
                try:
                    os.remove(api_cover_art.destination)
                except OSError:
                    pass
            try:
                api_data.update()
            except OSError as e:
                print(f"JSON ERR: {e}")
        except HTTPException as e:
            # 204 - No Content - Returned when nothing is or has been playing.
            # Not the same as being paused.
            if e.fetch.http_status == 204:
                current_view = 2

        if storage_error:
            screen.font = font.smart
            screen.pen = color.black
            screen.clear()
            screen.pen = color.red
            centre_text("Storage Error", cy - 45)
            screen.font = font.winds
            if sd_logo:
                screen.blit(sd_logo, vec2(screen.width / 2 - 16, cy - 27))
            screen.pen = color.white
            centre_text("Check the SD card", cy + 17, 1)
            centre_text("or change the album art", cy + 32, 1)
            centre_text("directory in config.", cy + 47, 1)
        else:
            t = min(1.0, time.ticks_diff(time.ticks_ms(), fade_start) / FADE_DURATION)
            t = easeInCubic(t)
            screen.alpha = 255
            screen.blit(tracks[(current_view + 1) % 2].render(), vec2(0, 0))
            screen.alpha = int(t * 255)
            screen.blit(tracks[current_view].render(), vec2(0, 0))

    else:
        screen.font = font.smart
        screen.pen = color.black
        screen.clear()
        screen.pen = color.red
        centre_text("Setup needed", cy - 50)
        screen.pen = color.blue
        centre_text("visit", cy - 10, 1)
        screen.pen = color.white
        centre_text(f"{config.wifi_hostname}.local", cy + 5, 2)
        screen.pen = color.blue
        centre_text("to configure", cy + 40, 1)
        centre_text("Now Playing", cy + 50, 1)
