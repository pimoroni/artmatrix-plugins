from plugins.maze import maze_manager

tilemap = None
floor = None
ceil = None
skybox = None
texture_pack = []


# Opening a file on littlefs to read 26 bytes costs ~2.4ms, and the same handful
# of paths recur every level change.
header_cache = {}


def png_header(path):
    header = header_cache.get(path)
    if header is None:
        with open(path, "rb") as file:
            head = file.read(26)
        if len(head) < 26 or head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        header = (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"), head[25] == 3)
        header_cache[path] = header
    return header


def load_texture(existing, path):
    """Decode into an existing buffer where it fits, otherwise allocate.

    load_into() takes its size from the target and rescales to fit, and skips
    every row when a palettised target meets a truecolour file - both silently -
    so the dimensions and the palette flag have to agree before reusing.
    """
    if existing is not None:
        header = png_header(path)
        if header is not None:
            width, height, indexed = header
            if existing.width == width and existing.height == height and existing.has_palette == indexed:
                existing.load_into(path)
                return existing
    return image.load(path)


class Level:
    @micropython.native
    def __init__(self, render_flags, level_map, floor_map, ceil_map, texture_path, floor_path, ceil_path, skybox_path, draw_fog, fog_resolution, fog_colour, background_colour, gradient):
        self.fog_level = render_flags & 0b11
        self.obscuring_fog = (render_flags >> 2) & 0b1
        self.draw_gradient = (render_flags >> 3) & 0b1
        self.draw_skybox = (render_flags >> 4) & 0b1
        self.draw_ceil = (render_flags >> 5) & 0b1
        self.draw_floor = (render_flags >> 6) & 0b1
        self.level_map = level_map
        self.floor_map = floor_map
        self.ceil_map = ceil_map
        self.texture_path = texture_path
        self.floor_path = floor_path
        self.ceil_path = ceil_path
        self.textures = texture_pack
        self.skybox_path = skybox_path
        self.draw_fog = draw_fog
        self.fog_resolution = fog_resolution
        self.fog_colour = color.rgb(*fog_colour)
        self.background_colour = color.rgb(*background_colour)
        screen.pen = self.fog_colour
        self.fog_pen = screen.pen
        screen.pen = self.background_colour
        self.background_pen = screen.pen
        self.gradient = (color.rgb(*gradient[0]), color.rgb(*gradient[1]), color.rgb(*gradient[2]), color.rgb(*gradient[3]))
        self.floor = floor
        self.ceil = ceil
        self.skybox = skybox

    @micropython.native
    def initialise(self):
        global floor, ceil, skybox, tilemap
        tilemap = load_texture(tilemap, self.texture_path)
        self.tilemap = tilemap
        texture_map = tilemap.spritesheet(16, 1)
        texture_pack.clear()
        for i in range(16):
            texture_pack.append(texture_map.sprite(i, 0))

        if self.draw_skybox:
            if self.skybox_path:
                skybox = load_texture(skybox, self.skybox_path)
                self.skybox = skybox
            else:
                skybox = None

        if self.draw_floor:
            if self.floor_path:
                floor = load_texture(floor, self.floor_path)
                self.floor = floor
            else:
                floor = None

        if self.draw_ceil:
            if self.ceil_path:
                ceil = load_texture(ceil, self.ceil_path)
                self.ceil = ceil
            else:
                ceil = None

    @micropython.native
    def get_value(self, pos, data):
        index = (int(pos.y) * self.level_map.x_size) + int(pos.x)
        return data[index]

    @micropython.native
    def texture(self, pos):
        return self.get_value(pos, self.level_map.texture_map)

    @micropython.native
    def endpoint(self, pos):
        return self.get_value(pos, self.level_map.endpoint_map)

    @micropython.native
    def walkable(self, pos):
        return self.get_value(pos, self.level_map.walkable_map)

    @micropython.native
    def height(self, pos):
        return self.get_value(pos, self.level_map.height_map)

    @micropython.native
    def backface(self, pos):
        return self.get_value(pos, self.level_map.backface_map)


class Map:
    @micropython.native
    def __init__(self, maps, x_size, y_size):
        texture, endpoint, walkable, height, backface = maps

        self.x_size = x_size
        self.y_size = y_size
        self.texture_map = texture
        self.endpoint_map = endpoint
        self.walkable_map = walkable
        self.height_map = height
        self.backface_map = backface


@micropython.native
def generate_maze(options, width, height):

    texture_set, draw_ceiling, draw_floor, draw_fog, fog_thickness, fog_resolution, obscuring_fog, draw_skybox, skybox, fog_colour, background_colour = options

    render_flags = 0b0
    render_flags += draw_floor
    render_flags = render_flags << 1
    render_flags += draw_ceiling
    render_flags = render_flags << 1
    render_flags += draw_skybox
    render_flags = render_flags << 1
    render_flags += 0
    render_flags = render_flags << 1
    render_flags += obscuring_fog
    render_flags = render_flags << 2
    render_flags += fog_thickness

    floor_map = 0
    ceil_map = 0
    texture_path = f"/lib/plugins/maze/assets/tex/wall_{texture_set}.png"
    floor_path = f"/lib/plugins/maze/assets/tex/floor_{texture_set}.png"
    ceil_path = f"/lib/plugins/maze/assets/tex/ceil_{texture_set}.png"
    skybox_path = f"/lib/plugins/maze/assets/tex/skybox_{skybox}.png"
    gradient = [
        [10, 12, 26],
        [58, 52, 74],
        [44, 38, 32],
        [14, 13, 12]
    ]

    texture, endpoints, walkable, height, backface, entities, startpoint, x_size, y_size = maze_manager.build_maze(width, height)
    maps = (texture, endpoints, walkable, height, backface)
    level_map = Map(maps, x_size, y_size)
    new_level = Level(render_flags, level_map, floor_map, ceil_map, texture_path, floor_path, ceil_path, skybox_path, draw_fog, fog_resolution, fog_colour, background_colour, gradient)

    return new_level, entities, startpoint
