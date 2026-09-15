import math
import time
import random

from plugins.after_yarrk import vector_sprite
from plugin_config import plugin_config

# Setting up a colour palette to use to draw the ships and sea
white = color.rgb(255, 255, 255)
grey = color.rgb(128, 128, 128)
light_brown = color.rgb(193, 154, 107)
brown = color.rgb(148, 110, 74)
dark_brown = color.rgb(102, 66, 40)
very_dark_brown = color.rgb(51, 33, 20)
cream = color.rgb(252, 247, 212)
shadow = color.rgb(0, 0, 0, 128)
yellow = color.rgb(247, 209, 77)
black = color.rgb(0, 0, 0)
dark_red = color.rgb(64, 0, 0)
ocean = color.rgb(13, 17, 38)  # color.rgb(26, 34, 76)

# These values are exposed to the web interface
cfg = plugin_config("after_yarrk", {
    "global_scale": 0.2,  # Overall scale of all ships and waves.
    "num_ships": 5,  # Number of ships total
    "sailing_angle": 330,  # Angle of sail - NOTE: doesn't change the angle the ships are pointing. 0 is in the x+ direction
    "bob_amount": 5.0,  # How much movement is added with the wing flapping motion.
    "travel_speed": 0.5,  # How fast the ships move across the screen.
    "spawn_border": 25,  # How many pixels outside outside the screen edges ships spawn / despawn. Tweak this if your other settings changes have made ships pop in / out
    "animation_speed": 25,  # The speed of the wing flapping animation and associated bobbing movement. Must be an integer.
    "wave_animation_speed": 25,
    "fps_limiter": True,  # Locks the simulation to max 30fps.
    "show_fps": False,  # Displays framerate in the top left corner of the screen.
})
global_scale = cfg["global_scale"]
num_ships = cfg["num_ships"]
sailing_angle = cfg["sailing_angle"]
bob_amount = cfg["bob_amount"]
travel_speed = cfg["travel_speed"]
spawn_border = cfg["spawn_border"]
animation_speed = cfg["animation_speed"]
wave_animation_speed = cfg["wave_animation_speed"]
fps_limiter = cfg["fps_limiter"]
show_fps = cfg["show_fps"]


try:
    with open("/lib/plugins/after_yarrk/config.html", "r", encoding="utf-8") as f:
        config_html = f.read()
except OSError as e:
    print(e)
    config_html = None

screen.antialias = image.X4


class Wave:
    wave_shape = [((-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23), (-22, 23)),
                  ((-24, 15), (-23, 15), (-22, 16), (-20, 16), (-18, 18), (-16, 19), (-15, 20), (-14, 22), (-14, 22), (-14, 22), (-14, 22), (-14, 22), (-15, 22), (-16, 21), (-17, 20), (-19, 20), (-20, 19), (-21, 18), (-23, 17)),
                  ((-27, 9), (-21, 12), (-17, 12), (-16, 15), (-10, 18), (-6, 23), (-3, 24), (-1, 29), (-6, 26), (-6, 26), (-11, 24), (-14, 22), (-15, 20), (-18, 19), (-19, 17), (-22, 16), (-24, 13), (-25, 12), (-26, 11)),
                  ((-30, 2), (-25, 5), (-21, 6), (-14, 8), (-7, 15), (-1, 16), (2, 22), (7, 28), (0, 26), (-5, 22), (-9, 21), (-11, 19), (-13, 17), (-14, 14), (-17, 13), (-21, 12), (-23, 10), (-25, 8), (-28, 6)),
                  ((-30, -6), (-24, -2), (-18, 0), (-12, 0), (-7, 5), (-1, 6), (13, 17), (16, 29), (12, 28), (10, 25), (6, 22), (2, 19), (-2, 15), (-6, 11), (-12, 9), (-15, 6), (-18, 3), (-22, 2), (-26, -1)),
                  ((-29, -11), (-20, -8), (-13, -4), (-7, 1), (2, 4), (13, 7), (18, 15), (28, 22), (16, 17), (11, 11), (7, 11), (3, 9), (-2, 5), (-7, 4), (-10, 3), (-12, 0), (-15, -2), (-19, -3), (-25, -5)),
                  ((-17, -14), (-16, -12), (-11, -11), (-3, -8), (3, -4), (11, -4), (13, 0), (22, 8), (17, 6), (8, 2), (3, 1), (0, -1), (-3, -5), (-6, -5), (-9, -6), (-12, -8), (-14, -11), (-16, -12), (-18, -12)),
                  ((-2, -13), (0, -13), (6, -9), (11, -9), (12, -7), (16, -6), (17, -4), (21, -1), (17, -1), (14, -3), (12, -5), (9, -6), (7, -6), (4, -7), (2, -8), (0, -9), (-2, -10), (1, -11), (-3, -12)),
                  ((5, -16), (7, -14), (10, -13), (14, -11), (15, -9), (17, -8), (21, -7), (23, -4), (21, -4), (20, -6), (18, -6), (17, -8), (15, -9), (13, -9), (11, -10), (10, -13), (7, -14), (4, -14), (3, -16)),
                  ((9, -17), (9, -17), (17, -14), (17, -14), (17, -14), (25, -10), (25, -10), (25, -10), (25, -10), (25, -10), (25, -10), (25, -10), (17, -14), (17, -14), (17, -14), (17, -14), (9, -17), (9, -17), (9, -17))]

    wave_sprite = vector_sprite.Vector_sprite(wave_shape)

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0

    def draw(self):
        sprite = self.wave_sprite.get_frame(self.t)
        sprite.transform = mat3().translate(self.x, self.y).scale(global_scale * 2)
        screen.pen = color.rgb(255, 255, 255, 192)
        screen.shape(sprite)
        self.t += wave_animation_speed


class Ship:
    # These class variables represent the custom shapes for the ship.
    # Each tuple within the group represents one frame of animation - the wing parts have eight keyframes,
    # the ship parts have only one (no animation).

    left_wing_parts = []
    ship_parts = []
    right_wing_parts = []

    right_wing = [((6, 6), (16, 0), (36, -6), (58, -6), (64, -2), (64, 2), (58, 12), (48, 12), (40, 10), (34, 12), (28, 12), (22, 8), (18, 10), (10, 10)),
                  ((2, 6), (14, 0), (26, 2), (38, 6), (56, 2), (60, 8), (56, 18), (42, 20), (36, 24), (26, 22), (22, 18), (14, 20), (6, 18), (2, 12)),
                  ((2, 6), (14, 0), (24, 6), (36, 16), (48, 20), (52, 26), (48, 32), (38, 32), (32, 36), (22, 36), (16, 32), (14, 24), (4, 22), (2, 12)),
                  ((2, 6), (18, 0), (24, 14), (34, 30), (42, 40), (38, 46), (30, 44), (24, 40), (20, 42), (14, 40), (10, 36), (10, 28), (2, 26), (2, 12)),
                  ((2, 6), (18, 0), (28, 10), (36, 20), (42, 36), (36, 44), (30, 44), (26, 38), (22, 36), (16, 36), (14, 30), (14, 24), (4, 22), (2, 12)),
                  ((2, 6), (18, 0), (32, 4), (44, 12), (52, 26), (50, 32), (44, 34), (38, 32), (34, 30), (30, 32), (22, 30), (20, 22), (12, 24), (6, 18)),
                  ((2, 6), (18, 0), (32, -2), (50, 2), (54, 6), (54, 12), (50, 16), (44, 16), (40, 14), (32, 18), (24, 16), (20, 12), (14, 14), (8, 14)),
                  ((2, 6), (18, 0), (36, -4), (52, -8), (62, -4), (64, 4), (54, 14), (46, 14), (38, 10), (34, 14), (28, 14), (22, 10), (18, 12), (8, 12))]

    left_wing = [((-2, -10), (-12, -4), (-18, -4), (-24, -4), (-26, -10), (-26, -16), (-30, -16), (-34, -24), (-32, -28), (-32, -34), (-34, -36), (-34, -42), (-30, -46), (-22, -44), (-14, -36), (-6, -22)),
                 ((-2, -8), (-14, -2), (-20, -2), (-32, -2), (-36, -6), (-34, -10), (-36, -10), (-42, -14), (-42, -20), (-40, -24), (-44, -30), (-44, -36), (-40, -40), (-32, -38), (-26, -28), (-14, -16)),
                 ((-2, -8), (-24, 2), (-30, 6), (-36, 4), (-40, 0), (-42, -2), (-48, -2), (-52, -8), (-50, -12), (-52, -18), (-52, -24), (-50, -28), (-46, -30), (-42, -28), (-34, -18), (-22, -12)),
                 ((-2, -8), (-14, 8), (-20, 10), (-22, 10), (-26, 16), (-30, 18), (-34, 18), (-36, 16), (-40, 16), (-44, 16), (-48, 14), (-48, 10), (-46, 8), (-38, 8), (-28, 4), (-18, -4)),
                 ((-2, -8), (-14, -2), (-18, 2), (-22, 2), (-24, 4), (-28, 6), (-32, 6), (-34, 4), (-38, 10), (-44, 10), (-46, 8), (-46, 2), (-44, 0), (-38, -2), (-30, -4), (-18, -8)),
                 ((-2, -8), (-14, -2), (-22, 0), (-28, 0), (-32, -6), (-36, -6), (-40, -8), (-42, -12), (-40, -16), (-46, -16), (-50, -20), (-50, -24), (-46, -28), (-38, -28), (-26, -24), (-14, -20)),
                 ((-2, -8), (-14, -2), (-24, -2), (-26, -8), (-24, -12), (-30, -12), (-34, -14), (-34, -20), (-32, -24), (-36, -26), (-38, -28), (-38, -32), (-34, -36), (-28, -38), (-20, -36), (-8, -24)),
                 ((-2, -8), (-14, -2), (-24, -2), (-28, -10), (-26, -16), (-32, -16), (-36, -20), (-36, -26), (-32, -28), (-32, -32), (-34, -34), (-34, -42), (-30, -46), (-26, -46), (-18, -42), (-8, -24))]

    shade_l1 = [((-32, -28), (-32, -34), (-32, -38), (-28, -40), (-24, -38), (-18, -30), (-28, -30)),
                ((-40, -24), (-44, -30), (-40, -32), (-34, -30), (-32, -28), (-32, -26), (-36, -26)),
                ((-50, -12), (-52, -18), (-48, -20), (-44, -20), (-40, -18), (-44, -16), (-48, -14)),
                ((-48, 14), (-48, 12), (-42, 14), (-38, 12), (-32, 12), (-36, 16), (-44, 16)),
                ((-46, 8), (-46, 4), (-42, 6), (-38, 6), (-34, 4), (-38, 10), (-44, 10)),
                ((-48, -18), (-46, -22), (-42, -24), (-36, -22), (-30, -18), (-40, -16), (-46, -16)),
                ((-36, -26), (-38, -28), (-34, -30), (-28, -30), (-22, -26), (-28, -26), (-32, -24)),
                ((-32, -32), (-34, -34), (-34, -38), (-24, -36), (-18, -32), (-24, -32), (-32, -28))]

    shade_l2 = [((-32, -20), (-30, -24), (-22, -26), (-14, -20), (-22, -18), (-26, -14), (-30, -16)),
                ((-42, -14), (-38, -18), (-30, -22), (-24, -16), (-30, -14), (-34, -10), (-36, -10)),
                ((-50, -4), (-40, -14), (-36, -14), (-30, -8), (-38, -6), (-42, -2), (-48, -2)),
                ((-36, 16), (-32, 12), (-22, 8), (-20, 10), (-26, 16), (-30, 18), (-34, 18)),
                ((-34, 4), (-28, 0), (-22, 0), (-22, 2), (-24, 4), (-28, 6), (-32, 6)),
                ((-40, -8), (-36, -12), (-30, -14), (-20, -14), (-28, -10), (-32, -6), (-36, -6)),
                ((-28, -18), (-24, -22), (-20, -24), (-16, -22), (-20, -16), (-24, -12), (-30, -12)),
                ((-32, -20), (-26, -26), (-20, -26), (-14, -22), (-22, -18), (-26, -16), (-32, -16))]

    shade_l3 = [((-24, -4), (-22, -10), (-14, -14), (-8, -6), (-12, -4)),
                ((-32, -2), (-34, -4), (-24, -10), (-18, -10), (-14, -2)),
                ((-30, 6), (-38, 2), (-32, -4), (-26, -6), (-24, 2)),
                ((-20, 10), (-22, 8), (-22, 6), (-8, 0), (-14, 8)),
                ((-18, 2), (-22, 2), (-22, -2), (-2, -8), (-16, 0)),
                ((-28, 0), (-26, -8), (-18, -10), (-10, -4), (-22, 0)),
                ((-24, -2), (-20, -10), (-14, -12), (-12, -8), (-14, -2)),
                ((-24, -2), (-20, -14), (-10, -14), (-6, -6), (-14, -2))]

    shade_r1 = [((6, 6), (22, 4), (22, 8), (18, 10), (10, 10)),
                ((6, 18), (16, 12), (22, 16), (22, 18), (14, 20)),
                ((4, 22), (2, 12), (12, 18), (16, 24), (14, 24)),
                ((2, 26), (2, 8), (8, 22), (12, 24), (10, 28)),
                ((4, 22), (2, 12), (10, 18), (14, 16), (14, 24)),
                ((6, 18), (2, 6), (12, 18), (20, 22), (12, 24)),
                ((8, 14), (2, 6), (10, 8), (20, 12), (14, 14)),
                ((8, 12), (2, 6), (24, 8), (22, 10), (18, 12))]

    shade_r2 = [((34, 12), (40, 10), (40, 2), (32, 8), (22, 4), (22, 8), (28, 12)),
                ((36, 24), (42, 20), (42, 12), (32, 18), (22, 16), (22, 18), (26, 22)),
                ((22, 36), (32, 36), (38, 32), (30, 30), (16, 24), (14, 24), (16, 32)),
                ((14, 40), (20, 42), (28, 38), (18, 36), (14, 32), (10, 26), (10, 36)),
                ((16, 36), (22, 36), (26, 28), (20, 30), (16, 28), (14, 24), (14, 30)),
                ((22, 30), (30, 32), (34, 30), (28, 28), (26, 20), (18, 12), (20, 22)),
                ((24, 16), (32, 18), (40, 14), (30, 14), (26, 10), (20, 6), (20, 12)),
                ((28, 14), (34, 14), (42, 10), (38, 6), (32, 8), (26, 4), (22, 10))]

    shade_r3 = [((48, 12), (58, 12), (64, 2), (56, 6), (50, 6), (48, 4), (40, 2), (40, 10)),
                ((42, 20), (56, 18), (60, 8), (56, 12), (50, 12), (46, 10), (40, 12), (38, 18)),
                ((38, 32), (48, 32), (52, 26), (46, 30), (42, 30), (38, 26), (32, 26), (30, 30)),
                ((30, 44), (38, 46), (42, 40), (34, 40), (30, 38), (28, 34), (24, 34), (24, 40)),
                ((30, 44), (36, 44), (42, 36), (36, 38), (32, 38), (28, 34), (22, 36), (26, 38)),
                ((44, 34), (50, 32), (52, 26), (44, 28), (42, 20), (34, 16), (38, 24), (38, 32)),
                ((44, 16), (50, 16), (54, 12), (48, 12), (44, 8), (34, 6), (38, 10), (40, 14)),
                ((46, 14), (54, 14), (64, 4), (56, 8), (52, 6), (44, 4), (38, 6), (38, 10))]

    main_deck = [((2, -10), (14, -18), (24, -22), (39, -34), (41, -32), (27, -10), (25, -6), (13, 3), (6, 7), (5, 4), (5, 1), (-9, -3))]
    hull = [((28, -14), (27, -4), (25, 6), (15, 17), (2, 27), (-20, 34), (-33, 44), (-36, 31), (-32, 21), (-32, 12), (-35, 4), (-11, 3), (-11, 8), (7, 0), (7, 6), (18, -1))]
    lower_hull = [((-32, 15), (-13, 18), (4, 15), (19, 6), (27, -4), (25, 6), (15, 17), (2, 27), (-20, 34), (-33, 44), (-36, 31), (-32, 21))]
    sail = [((-24, -44), (-24, -31), (-27, -21), (-5, -14), (30, -3), (32, -15), (30, -35), (24, -46), (-28, -58))]
    skull = [((-12, -40), (-11, -33), (-6, -30), (-5, -28), (-6, -20), (4, -16), (4, -25), (8, -27), (14, -30), (14, -37), (8, -45), (-5, -48), (-10, -44), (-12, -40), (-9, -40), (-6, -43), (-4, -40), (-2, -39), (3, -38), (6, -39), (9, -41), (11, -36), (9, -34), (5, -35), (1, -29), (-3, -30), (0, -35), (1, -29), (5, -35), (3, -38), (-2, -39), (-5, -36), (-9, -37), (-9, -40))]
    mast = [((-5, -56), (-3, -56), (-3, -45), (25, -38), (25, -37), (-3, -42), (-3, -22), (31, -11), (31, -10), (-3, -19), (-2, 0), (-6, 0), (-5, -20), (-27, -28), (-27, -29), (-5, -23), (-5, -43), (-28, -50), (-28, -51), (-5, -46))]
    mid_deck = [((-10, -6), (7, 0), (-11, 8), (-12, 3), (-17, 0), (-21, -1))]
    poop = [((-21, -2), (-45, 0), (-35, 4), (-11, 3))]
    stripe = [((27, -9), (27, -4), (14, 15), (0, 21), (-19, 25), (-34, 25), (-32, 15), (-13, 18), (8, 13), (17, 4))]
    back = [((-45, 0), (-31, 5), (-27, 10), (-27, 22), (-35, 35), (-46, 18), (-48, 7))]
    windows = [((-45, 5), (-45, 10), (-41, 11), (-41, 6), (-37, 7), (-37, 12), (-31, 13), (-31, 8), (-25, 8), (-25, 12), (-19, 13), (-19, 9), (-14, 10), (-14, 14), (-8, 13), (-8, 9), (-4, 8), (-4, 12), (5, 9), (5, 5), (0, -6), (-6, -4), (-2, -2), (5, 2), (0, 4), (-9, 0), (-2, -2), (-6, -4), (-12, -2), (-15, -3), (-22, -3), (-16, 0), (-30, 1), (-38, -1), (-22, -3), (-15, -3), (-20, -6), (-15, -8), (-6, -4), (0, -6), (3, -8), (5, -9), (10, -7), (7, -5), (4, -3), (14, 1), (17, -1), (7, -5), (10, -7), (19, -3), (22, -6), (13, -9), (10, -7), (5, -9), (8, -11), (1, -14), (-1, -12), (5, -9), (3, -8), (-2, -10), (-2, -7), (0, -6), (5, 5), (-4, 8), (-8, 9), (-14, 10), (-19, 9), (-25, 8), (-31, 8), (-37, 7), (-41, 6))]

    # These are added into their relevant lists of parts for convenience, converted into a Vector_sprite object and stored in a tuple along with the palette colour to draw the shape in.
    left_wing_parts.append((vector_sprite.Vector_sprite(left_wing), white))
    left_wing_parts.append((vector_sprite.Vector_sprite(shade_l1), grey))
    left_wing_parts.append((vector_sprite.Vector_sprite(shade_l2), grey))
    left_wing_parts.append((vector_sprite.Vector_sprite(shade_l3), grey))

    ship_parts.append((vector_sprite.Vector_sprite(main_deck), light_brown))
    ship_parts.append((vector_sprite.Vector_sprite(hull), brown))
    ship_parts.append((vector_sprite.Vector_sprite(lower_hull), shadow))
    ship_parts.append((vector_sprite.Vector_sprite(sail), cream))
    ship_parts.append((vector_sprite.Vector_sprite(skull), dark_red))
    ship_parts.append((vector_sprite.Vector_sprite(mast), dark_brown))
    ship_parts.append((vector_sprite.Vector_sprite(mid_deck), light_brown))
    ship_parts.append((vector_sprite.Vector_sprite(poop), light_brown))
    ship_parts.append((vector_sprite.Vector_sprite(stripe), yellow))
    ship_parts.append((vector_sprite.Vector_sprite(back), very_dark_brown))
    ship_parts.append((vector_sprite.Vector_sprite(windows), black))

    right_wing_parts.append((vector_sprite.Vector_sprite(right_wing), white))
    right_wing_parts.append((vector_sprite.Vector_sprite(shade_r1), grey))
    right_wing_parts.append((vector_sprite.Vector_sprite(shade_r2), grey))
    right_wing_parts.append((vector_sprite.Vector_sprite(shade_r3), grey))

    shadow_shape = shape.circle(0, 0, 40)

    # Precalculating a few useful quantities that only change between restarts of the program and are common to all instances of the ship.
    sailing_angle_rad = math.radians(sailing_angle)
    direction_vector = vec2(math.cos(sailing_angle_rad), math.sin(sailing_angle_rad))
    spawn_aspect_ratio = min(abs(direction_vector.x), abs(direction_vector.y)) / max(abs(direction_vector.x), abs(direction_vector.y))
    normal_vector = vec2(-direction_vector.y, direction_vector.x)

    # Initialising just runs the same respawn logic as reset()
    def __init__(self):
        self.reset()

    @micropython.native
    def reset(self):
        # If the sailing angle isn't 45 degrees, we don't want the ships to spawn equally along each edge.
        # So if it's more horizontal than vertical, we want more ships spawning on the left edge than the bottom to look good.
        # We can get this from the ratio of the components of the sailing direction vector, then use that as the threshold for a random number to hit below or above.

        spawn_seed = random.uniform(0, 1)

        if spawn_seed < self.spawn_aspect_ratio:
            x = -spawn_border
            y = random.randint(spawn_border, 128 + spawn_border)
        else:
            y = 128 + spawn_border
            x = random.randint(-spawn_border, 128 - spawn_border)

        self.pos = vec2(x, y)

        # rotated_y is essentially how far to the right the ship is from the ship's point of view - its y position rotated by the direction of travel.
        # It's used to determine the draw order of the ships in case of overlaps.
        self.rotated_y = (self.pos.y * self.direction_vector.x) - (self.pos.x * self.direction_vector.y)

        # scale is just dependent on how far down the screen the ship is. Phase determines which animation frame the wings start on, and bob_phase is the same value mapped from 0 to 1 to animate the bobbing in sync with the wings.
        self.scale = ((int(self.pos.y) / 150) ** 2) + 1
        self.phase = random.randint(0, 7)
        self.bob_phase = self.phase / 8

    @micropython.native
    def move(self):
        # Moving is pretty self explanatory, but scale is recalculated every frame so that ships shrink away with perspective.
        self.pos += self.direction_vector * travel_speed * self.scale
        self.scale = ((int(self.pos.y) / 150) ** 2) + 1

        # If we've reached the right or top of the screen, respawn.
        if self.pos.x > 128 + spawn_border or self.pos.y < -spawn_border:
            self.reset()

    @micropython.native
    def draw(self, t):
        final_scale = global_scale * self.scale

        # bob_amount provides us with a sine wave from -1 to 1 based on the animation frame and the ship's animation phase.
        # It gets multiplied up and added to the ship's y position as an offset.
        bob_position = math.cos(((t / 800) * (2 * math.pi)) + (self.bob_phase * (2 * math.pi)))
        bob_offset = bob_amount * final_scale * bob_position
        bobbing_y = self.pos.y + bob_offset
        bobbing_x = self.pos.x - bob_offset

        # Creating the final transformation matrix to use for all of the ship's parts, as well as the final value of the animation frame to get, offset by the ship's animation phase.
        ship_transform = mat3().translate(bobbing_x, bobbing_y).scale(final_scale)
        final_t = (t + (self.phase * 100)) % 800

        # The shadow doesn't bob with the ship so it uses the base y position as a base, but it does grow and shrink slightly using that y offset value.
        shadow_scale = final_scale * (0.5 + ((bob_position * bob_amount) + bob_amount) / 64)
        shadow_transform = mat3().translate(bobbing_x, self.pos.y + (50 * final_scale)).rotate(333).scale(shadow_scale, shadow_scale / 3)
        self.shadow_shape.transform = shadow_transform
        screen.pen = shadow
        screen.shape(self.shadow_shape)

        # Now we get the appropriate animation frames for each vector shape, colour them and draw them.
        # We could just list them all in one list as long as they're in the right order, but splitting them up is just
        # a little easier to understand.
        for wing_part in self.left_wing_parts:
            vector_sprite, colour = wing_part
            sprite = vector_sprite.get_frame(final_t)
            sprite.transform = ship_transform
            screen.pen = colour
            screen.shape(sprite)

        for ship_part in self.ship_parts:
            vector_sprite, colour = ship_part
            sprite = vector_sprite.get_frame(final_t)
            sprite.transform = ship_transform
            screen.pen = colour
            screen.shape(sprite)

        for wing_part in self.right_wing_parts:
            vector_sprite, colour = wing_part
            sprite = vector_sprite.get_frame(final_t)
            sprite.transform = ship_transform
            screen.pen = colour
            screen.shape(sprite)


last_frame = time.ticks_ms()
screen.font = rom_font.sins

waves = []
ships = []
for _i in range(num_ships):
    ships.append(Ship())

t = 0


# In the main loop we've set up a frame limiter at around 30fps.
# Each frame we just clear the screen, and then draw every ship.
def update():
    global t, last_frame

    now = time.ticks_ms()
    frametime = now - last_frame

    if frametime >= 33 or not fps_limiter:
        last_frame = now
        fps = 1000 / frametime

        t += animation_speed
        t %= 800

        screen.pen = ocean
        screen.clear()

        for wave in waves:
            wave.draw()

        for wave in reversed(waves):
            if wave.t > 1000:
                waves.remove(wave)

        if not random.randint(0, 10):
            waves.append(Wave(random.randint(0, 128), random.randint(0, 128)))

        for ship in ships:
            ship.move()

        ships.sort(key=lambda x: x.rotated_y)

        for ship in ships:
            ship.draw(t)

        if show_fps:
            screen.pen = color.rgb(0, 0, 0)
            screen.rectangle(0, 0, 45, 12)

            screen.font = rom_font.sins
            screen.pen = color.red
            screen.text(str(fps), 0, 0)
