import math

W = screen.width
H = screen.height
aspect_ratio = W / H

furthest_wall = 0
wall_shadow_colour = color.rgb(28, 28, 28)
screen.pen = wall_shadow_colour
wall_shadow_pen = screen.pen

draw_walls_debug = True
full_range_entities_debug = False

wall_fog_palettes = []
floor_fog_palettes = []
ceil_fog_palettes = []
# Keyed on everything a ramp derives from. Unbounded, but the key space is the
# preset table.
fog_palette_cache = {}


def fog_palettes(source, path, fog_colour, fog_maximum, steps, offset):
    key = (path, fog_colour.p, fog_maximum, steps, offset)
    built = fog_palette_cache.get(key)
    if built is None:
        built = []
        for i in range(steps + 1):
            alpha = int(fog_maximum * i / steps) + offset
            if alpha > fog_maximum:
                alpha = fog_maximum
            built.append(palette(overlay(source.palette, fog_colour, alpha)))
        fog_palette_cache[key] = built
    return built


def generate_fog_palettes(level):
    global wall_fog_palettes, floor_fog_palettes, ceil_fog_palettes
    wall_fog_palettes = []
    floor_fog_palettes = []
    ceil_fog_palettes = []
    if not level.draw_fog:
        return

    fog_maximum = 255 if level.obscuring_fog else 205
    steps = level.fog_resolution
    fog_colour = level.fog_colour

    wall_fog_palettes = fog_palettes(level.tilemap, level.texture_path, fog_colour, fog_maximum, steps, 0)
    if level.draw_floor and level.floor is not None and level.floor.has_palette:
        floor_fog_palettes = fog_palettes(level.floor, level.floor_path, fog_colour, fog_maximum, steps, 20)
    if level.draw_ceil and level.ceil is not None and level.ceil.has_palette:
        ceil_fog_palettes = fog_palettes(level.ceil, level.ceil_path, fog_colour, fog_maximum, steps, 20)


@micropython.native
def overlay(palette, blend, alpha):
    alpha /= 255
    blend_r = alpha * blend.r
    blend_g = alpha * blend.g
    blend_b = alpha * blend.b
    inv_alpha = 1 - alpha

    new_palette = []

    for col in palette:
        r = (inv_alpha * col.r) + blend_r
        g = (inv_alpha * col.g) + blend_g
        b = (inv_alpha * col.b) + blend_b
        new_palette.append(color.rgb(r, g, b, col.a))

    return new_palette


@micropython.native
def draw_walls(player, level, render_queue, hit_depth):
    global furthest_wall

    map_width = level.level_map.x_size
    map_height = level.level_map.y_size
    texture_map = level.level_map.texture_map
    height_map = level.level_map.height_map
    endpoint_map = level.level_map.endpoint_map
    backface_map = level.level_map.backface_map

    dirx = player.vector_x
    diry = player.vector_y
    px = player.x
    py = player.y
    z_height = H * (player.height - 0.5)
    base_mapx = player.grid_x
    base_mapy = player.grid_y
    y_factor = 0.495 * aspect_ratio

    planex, planey = -diry * y_factor, dirx * y_factor
    render_queue.clear()

    furthest_wall = 0
    furthest_wall_top = 0
    furthest_wall_btm = screen.height
    left_ray_x = 0
    left_ray_y = 0
    right_ray_x = 0
    right_ray_y = 0

    camera = 0
    rayx = 0
    rayy = 0
    mapx = 0
    mapy = 0
    ddx = 0
    ddy = 0
    stepx = 0
    stepy = 0
    sidex = 0
    sidey = 0
    map_index = None
    tex_index = None
    previous_texture = None
    draw_backface = 0
    endpoint = 0
    side = 0
    dist = 0
    top = 0
    height = 0
    u = 0
    height_property = 0
    i = 0
    max_i = W * hit_depth

    for x in range(W):
        camera = ((2 * x) / W) - 1

        rayx = dirx + planex * camera
        rayy = diry + planey * camera

        if x == 0:
            left_ray_x = rayx
            left_ray_y = rayy
        if x == W - 1:
            right_ray_x = rayx
            right_ray_y = rayy

        mapx, mapy = base_mapx, base_mapy

        ddx = abs(1 / rayx) if rayx != 0 else 1e30
        ddy = abs(1 / rayy) if rayy != 0 else 1e30

        if rayx < 0:
            stepx = -1
            sidex = (px - mapx) * ddx
        else:
            stepx = 1
            sidex = (mapx + 1 - px) * ddx
        if rayy < 0:
            stepy = -1
            sidey = (py - mapy) * ddy
        else:
            stepy = 1
            sidey = (mapy + 1 - py) * ddy

        side = 0
        map_index = (map_width * mapy) + mapx
        tex_index = texture_map[map_index]
        previous_texture = tex_index
        draw_backface = backface_map[map_index]
        height_property = height_map[map_index]

        while i < max_i:
            if sidex < sidey:
                sidex += ddx
                mapx += stepx
                side = 0
            else:
                sidey += ddy
                mapy += stepy
                side = 1

            if mapx < 0 or mapy < 0 or mapx >= map_width or mapy >= map_height:
                break

            map_index = (map_width * mapy) + mapx
            tex_index = texture_map[map_index]
            endpoint = endpoint_map[map_index]
            height_property = height_map[map_index]
            if tex_index or draw_backface:
                if side == 0:
                    dist = sidex - ddx
                    u = py + (dist * rayy)
                    u -= int(u)
                    if rayx < 0:
                        u = 1 - u
                else:
                    dist = sidey - ddy
                    u = px + (dist * rayx)
                    u -= int(u)
                    if rayy > 0:
                        u = 1 - u

                if dist < 0.0001:
                    dist = 0.0001

                height = H / dist
                top = (H - height) / 2
                top += z_height / dist

                top = math.floor(top)
                height = math.floor(height)

                dist = float(dist)

                if dist > furthest_wall:
                    furthest_wall = dist

                if top > furthest_wall_top:
                    furthest_wall_top = top
                if top + height < furthest_wall_btm:
                    furthest_wall_btm = top + height

                if tex_index and (endpoint or not previous_texture):
                    render_queue.append((dist, x, side, u, top, height, height_property, tex_index))

                if draw_backface == 1 or (draw_backface == 2 and not tex_index):
                    render_queue.append((dist - 0.001, x, side, 1 - u, top, height, height_property, previous_texture))

                i += 1

            draw_backface = backface_map[map_index]
            previous_texture = tex_index

            if endpoint:
                break

    screen_centre = H / 2
    draw_floor = level.draw_floor
    draw_ceil = level.draw_ceil
    horz_strips = []
    if draw_floor:
        for y in range(furthest_wall_btm, H + 2):
            horz_strips.append(y)
    if draw_ceil:
        for y in range(furthest_wall_top + 2):
            horz_strips.append(y)

    for y in horz_strips:
        z_offset = math.copysign(z_height, y - screen_centre)
        if z_height < 0:
            y_row = abs(y - screen_centre)
            if y_row == 0:
                y_row = 0.001
            dist = (screen_centre - (z_offset)) / y_row
        else:
            y_row = abs(y - 1 - screen_centre)
            if y_row == 0:
                y_row = 0.001
            dist = (screen_centre + (z_offset)) / y_row
        slice_step_x = dist * (right_ray_x - left_ray_x)
        slice_step_y = dist * (right_ray_y - left_ray_y)
        slice_start_x = player.x + dist * left_ray_x
        slice_start_y = player.y + dist * left_ray_y
        slice_end_x = slice_start_x + slice_step_x
        slice_end_y = slice_start_y + slice_step_y
        render_queue.append((dist + 0.01, y - 2, slice_start_x, slice_start_y, slice_end_x, slice_end_y))


@micropython.native
def draw_entities(render_queue, player, entity_list):
    px = player.x
    py = player.y
    vx = player.vector_x
    vy = player.vector_y
    W = screen.width
    H = screen.height
    y_factor = 0.495 * aspect_ratio
    cone = 0.707 * 0.707
    cull_dist = furthest_wall - 1

    for entity_id, entity in enumerate(entity_list):
        rel_x = entity.x - px
        rel_y = entity.y - py

        forward = (rel_x * vx) + (rel_y * vy)
        if forward <= 0:
            continue
        if (forward * forward) < cone * ((rel_x * rel_x) + (rel_y * rel_y)):
            continue

        dist = forward + 0.0001  # This avoids divide by 0 errors if the entity is exactly on the player's view plane

        if not full_range_entities_debug:
            if dist >= cull_dist:
                continue

        lateral = (rel_y * vx) - (rel_x * vy)
        x = ((((lateral / forward) / y_factor) + 1) * W) / 2

        dim = H / dist
        if x < -dim or x > W + (dim / 2):
            continue
        render_queue.append((dist, x, entity_id, vec2(rel_x, rel_y)))


@micropython.native
def render(render_queue, player, level, entity_list, fog_levels, texture_size):
    W = screen.width
    H = screen.height
    z_height = H * (player.height - 0.5)
    textures = level.textures
    floor = level.floor
    ceil = level.ceil
    angle = player.angle
    fog_resolution = level.fog_resolution
    draw_fog = level.draw_fog
    walls_debug = draw_walls_debug
    fog_pen = level.fog_pen

    screen.pen = level.background_pen
    screen.clear()

    if level.obscuring_fog:
        screen.pen = fog_pen
        screen.clear()

    if level.draw_gradient:
        top, top_centre, btm, btm_centre = level.gradient
        screen.pen = brush.gradient(brush.LINEAR, 0, 0, 0, H // 2, [(0.0, top), (1.0, top_centre)])
        screen.rectangle(0, 0, W, H // 2)
        screen.pen = brush.gradient(brush.LINEAR, 0, H // 2, 0, H, [(0.0, btm_centre), (1.0, btm)])
        screen.rectangle(0, H // 2, W, H - H // 2)

    if level.draw_skybox:
        sbw = level.skybox.width
        left = ((angle + math.pi) / (2 * math.pi)) * sbw
        overlap = left + W - sbw
        if overlap <= 0:
            rendered_skybox = level.skybox.window(int(left), 0, W, H)
            screen.blit(rendered_skybox, 0, 0)
        else:
            rendered_skybox_a = level.skybox.window(int(left), 0, W - overlap, H)
            rendered_skybox_b = level.skybox.window(0, 0, overlap, H)
            screen.blit(rendered_skybox_a, 0, 0)
            screen.blit(rendered_skybox_b, W - overlap, 0)

    tilemap = level.tilemap
    fog_index_mul = 0
    wall_next = -1e30
    floor_next = -1e30
    ceil_next = -1e30

    if draw_fog:
        fog_increment = fog_levels[level.fog_level] / fog_resolution
        current_entity_fog_level = fog_resolution
        if len(entity_list) > 0:
            entity_list[0].set_texture_palette(current_entity_fog_level)
        fog_index_mul = fog_resolution / fog_levels[level.fog_level]
        wall_next = 1e30
        floor_next = 1e30
        ceil_next = 1e30

    render_queue.sort()

    for item in reversed(render_queue):
        if len(item) == 4:
            dist, x, entity_id, angle = item
            entity = entity_list[entity_id]

            if draw_fog:
                fog_level = dist // fog_increment
                if fog_level >= fog_resolution:
                    pass
                elif fog_level < current_entity_fog_level:
                    current_entity_fog_level = fog_level
                    entity.set_texture_palette(fog_level)

            texture = entity.serve_texture(angle)
            dim = H / dist
            x -= dim / 2
            y = ((H / 2) - ((dim * 0.86) / 2)) + (z_height / dist)

            screen.blit(texture, rect(x, y, dim, dim))

        elif len(item) == 6:
            dist, y_height, start_x, start_y, end_x, end_y = item

            start_x /= (floor.width / texture_size)
            start_y /= (floor.height / texture_size)
            end_x /= (floor.width / texture_size)
            end_y /= (floor.height / texture_size)
            if y_height > H / 2:
                texture = floor
            else:
                texture = ceil

            if texture is None:
                continue

            if texture is floor:
                if dist < floor_next and floor_fog_palettes:
                    fog_index = int(dist * fog_index_mul)
                    if fog_index > fog_resolution:
                        fog_index = fog_resolution
                    texture.palette = floor_fog_palettes[fog_index]
                    floor_next = fog_index / fog_index_mul
            elif dist < ceil_next and ceil_fog_palettes:
                fog_index = int(dist * fog_index_mul)
                if fog_index > fog_resolution:
                    fog_index = fog_resolution
                texture.palette = ceil_fog_palettes[fog_index]
                ceil_next = fog_index / fog_index_mul

            screen.blit_hspan(texture, 0, y_height, W, start_x, start_y, end_x, end_y)

        elif walls_debug:
            dist, x, side, u, y0, y1, h, tex_index = item

            texture = textures[tex_index - 1]

            if dist < wall_next:
                fog_index = int(dist * fog_index_mul)
                if fog_index > fog_resolution:
                    fog_index = fog_resolution
                tilemap.palette = wall_fog_palettes[fog_index]
                wall_next = fog_index / fog_index_mul

            if h == 0:
                screen.blit_vspan(texture, x, int((H / 2) + (z_height / dist)), int(y1 / 2), u, 0.5, u, 1)
            elif h == 1:
                screen.blit_vspan(texture, x, y0, y1, u, 0, u, 1)
            elif h == 2:
                screen.blit_vspan(texture, x, y0, y1, u, 0, u, 1)
                screen.blit_vspan(texture, x, y0 - y1, y1, u, 0, u, 1)
            elif h == 3:
                screen.blit_vspan(texture, x, y0, y1, u, 0, u, 1)
                screen.blit_vspan(texture, x, y0 - (2 * y1), (2 * y1), u, -1, u, 1)

            if h == 0:
                shadow_start = int((H / 2) + (z_height / dist))
                shadow_height = int(y1 / 2)
            elif h == 1:
                shadow_start = y0
                shadow_height = y1
            elif h == 2:
                shadow_start = y0 - y1
                shadow_height = y1 * 2
            elif h == 3:
                shadow_start = y0
                shadow_height = y1
                while shadow_start > 0:
                    shadow_start -= y1
                    shadow_height += y1

            if side == 1:
                screen.pen = wall_shadow_pen
                screen.alpha = 40
                screen.vspan(x, shadow_start, shadow_height + 1)
                screen.alpha = 255
