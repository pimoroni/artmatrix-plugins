import random

# Every cell starts as wall. Cached so a level change copies this rather than
# rebuilding the fill pattern.
_solid = None


NEIGHBOUR_CHOICES = tuple(
    tuple(d for d in range(4) if mask & (1 << d)) for mask in range(16)
)


def _new_maze_map(size):
    global _solid
    if _solid is None or len(_solid) != size:
        _solid = b"\x01" * size
    return bytearray(_solid)


class Maze:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rows = width
        self.stride = height
        self.maze_map = _new_maze_map(width * height)

    @micropython.native
    def render(self):
        maze_map = self.maze_map
        y_size = self.rows
        x_size = self.stride
        size = x_size * y_size

        texture = bytearray(size)
        endpoints = bytearray(size)
        walkable = bytearray(size)
        heights = bytearray(size)
        backface = bytearray(size)
        entities = []

        min_x = 3
        max_x = x_size - 4
        min_y = 3
        max_y = y_size - 4

        i = 0
        for y in range(y_size):
            in_y = min_y <= y <= max_y
            for x in range(x_size):
                if maze_map[i]:
                    gap = not random.randint(0, 10)
                    in_bounds = in_y and min_x <= x <= max_x
                    if gap and in_bounds:
                        walkable[i] = 1
                    else:
                        seed = random.randint(0, 15)
                        if seed == 0:
                            if in_bounds:
                                entities.append((random.randint(0, 4), x + 0.5, y + 0.5))
                            else:
                                seed = 1
                        if seed:
                            texture[i] = seed + 1
                            endpoints[i] = 1
                            heights[i] = 1
                else:
                    walkable[i] = 1
                i += 1

        startpoint = vec2((self.width - 1) // 2, (self.height - 1) // 2)

        return (texture, endpoints, walkable, heights, backface, entities, startpoint, x_size, y_size)


@micropython.native
def build_maze(width, height):
    if width <= 0:
        raise ValueError("width out of range. Expected greater than 0")
    if width % 2 == 0:
        width += 1

    if height <= 0:
        raise ValueError("height out of range. Expected greater than 0")
    if height % 2 == 0:
        height += 1

    maze = Maze(width, height)
    maze_map = maze.maze_map
    stride = maze.stride
    rows = maze.rows
    two_rows = 2 * stride

    x = (width - 1) // 2
    y = (height - 1) // 2
    maze_map[y * stride + x] = 0
    stack = [x, y]

    while stack:
        base = y * stride + x
        neighbours = 0
        if y > 2 and maze_map[base - two_rows]:
            neighbours = 1
        if y < rows - 3 and maze_map[base + two_rows]:
            neighbours |= 2
        if x > 2 and maze_map[base - 2]:
            neighbours |= 4
        if x < stride - 3 and maze_map[base + 2]:
            neighbours |= 8

        if neighbours == 0:
            y = stack.pop()
            x = stack.pop()
            continue

        direction = random.choice(NEIGHBOUR_CHOICES[neighbours])

        if direction == 0:
            maze_map[base - stride] = 0
            maze_map[base - two_rows] = 0
            y -= 2
        elif direction == 1:
            maze_map[base + stride] = 0
            maze_map[base + two_rows] = 0
            y += 2
        elif direction == 2:
            maze_map[base - 1] = 0
            maze_map[base - 2] = 0
            x -= 2
        else:
            maze_map[base + 1] = 0
            maze_map[base + 2] = 0
            x += 2

        stack.append(x)
        stack.append(y)

    return maze.render()
