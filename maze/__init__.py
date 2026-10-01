import time
import random
import gc
import math
import json

from plugins.maze import renderer
from plugins.maze import entity_manager
from plugins.maze import level_manager
from plugin_config import plugin_config

screen.font = font.sins
screen.pen = color.black
screen.clear()

presets = {
    "lv426": {
        "texture_set": "scifi",
        "props_set": "scifi",
        "draw_ceiling": True,
        "draw_floor": True,
        "draw_skybox": False,
        "skybox": "stars",
        "draw_fog": True,
        "fog_resolution": 10,
        "fog_thickness": 2,
        "obscuring_fog": True,
        "fog_colour": (0, 0, 0),
        "background_colour": (0, 0, 0)
    },
    "lost_empire": {
        "texture_set": "castle",
        "props_set": "garden",
        "draw_ceiling": False,
        "draw_floor": True,
        "draw_skybox": False,
        "skybox": "bluesky",
        "draw_fog": True,
        "fog_resolution": 10,
        "fog_thickness": 1,
        "obscuring_fog": True,
        "fog_colour": (225, 232, 255),
        "background_colour": (225, 232, 255)
    },
    "neon": {
        "texture_set": "neon",
        "props_set": "neon",
        "draw_ceiling": False,
        "draw_floor": True,
        "draw_skybox": True,
        "skybox": "vaporwave",
        "draw_fog": False,
        "fog_resolution": 10,
        "fog_thickness": 0,
        "obscuring_fog": False,
        "fog_colour": (0, 0, 0),
        "background_colour": (0, 0, 0)
    }
}

presets_json = json.dumps(presets)

player_walk_speed = 0.75
player_turn_speed = 1
player_height = 0.6  # Height of the player from the floor, in blocks. Limit from 0 < X < 1.
draw_props = True

# Options
cfg = plugin_config("maze", {
    "maze_period": 5,  # The number of minutes between changes, 0 for no change. Only applies when preset is random.
    "preset": "random",  # Options: lv426, lost_empire, neon, random
    "show_fps": False,
})
maze_period = cfg["maze_period"]
preset = cfg["preset"]
if preset != "random" and preset not in presets:
    preset = "random"
show_fps = cfg["show_fps"]


angles = (0, math.pi / 2, math.pi, math.pi + math.pi / 2)


def process_options():
    if preset == "random":
        active = presets[random.choice(list(presets.keys()))]
    else:
        active = presets[preset]

    options = [
        active["texture_set"],
        active["draw_ceiling"],
        active["draw_floor"],
        active["draw_fog"],
        active["fog_thickness"],
        active["fog_resolution"],
        active["obscuring_fog"],
        active["draw_skybox"],
        active["skybox"],
        active["fog_colour"],
        active["background_colour"]
    ]

    return options, active["props_set"]


@micropython.native
def refresh_level():
    options, props = process_options()
    new_level, entities, startpoint = level_manager.generate_maze(options, 64, 64)
    new_level.initialise()
    props_path = f"/lib/plugins/maze/assets/tex/props_{props}.png"
    entity_manager.prop_texture_bank = level_manager.load_texture(entity_manager.prop_texture_bank, props_path)
    entity_manager.prop_texture_bank_sheet = entity_manager.prop_texture_bank.spritesheet(16, 5)
    entity_manager.generate_palettes(new_level.obscuring_fog, new_level.fog_colour, new_level.fog_resolution, props_path)
    renderer.generate_fog_palettes(new_level)
    gc.collect()
    new_entity_list = []
    for entity in entities:
        entity_type, x, y = entity
        new_entity_list.append(entity_manager.Prop(x, y, entity_type, angle=random.choice(angles)))
    new_player = entity_manager.Monster("/lib/plugins/maze/assets/entities/player.json")
    new_player.x = startpoint.x + 0.5
    new_player.y = startpoint.y + 0.5
    new_player.move_speed = player_walk_speed / 10
    new_player.turn_speed = player_turn_speed / 10
    new_player.set_neighbour_target(new_level)
    new_player.height = player_height

    return new_level, new_player, new_entity_list


fog_levels = [10, 7, 5, 3]
texture_size = 64
hit_depth = 5
render_queue = []
current_level, player1, new_entity_list = refresh_level()
entity_manager.entity_list = new_entity_list

screen.pen = color.red
fps_pen = screen.pen

last_frame = time.ticks_ms()
last_change_time = time.ticks_ms()
max_frametime = 0
min_frametime = 999999
max_queue_len = 0
min_queue_len = 999999


def update():
    global current_level, player1, new_entity_list, last_frame, last_change_time

    now = time.ticks_ms()
    frametime = now - last_frame

    change_time = now - last_change_time
    if preset == "random" and maze_period > 0 and change_time >= maze_period * 60000:
        current_level, player1, new_entity_list = refresh_level()
        entity_manager.entity_list = new_entity_list
        last_change_time = now
    else:
        player1.grid_roam(current_level)
        renderer.draw_walls(player1, current_level, render_queue, hit_depth)
        if draw_props:
            renderer.draw_entities(render_queue, player1, entity_manager.entity_list)
        renderer.render(render_queue, player1, current_level, entity_manager.entity_list, fog_levels, texture_size)

        last_frame = now

    if show_fps:
        fps = 1000 / frametime if frametime else 0
        screen.pen = fps_pen
        screen.text(f"{fps:.0f}fps", 0, 0)
