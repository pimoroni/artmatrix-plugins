import math
import json
import random

two_pi = math.pi * 2
pi_over_two = math.pi / 2
angle_adjust = math.pi / 16
W = screen.width
H = screen.height

prop_texture_bank = None
prop_texture_bank_sheet = None
palettes = []
entity_list = []
palette_cache = {}


@micropython.native
def generate_palettes(obscuring_fog, fog_colour, fog_levels, path):
    global palettes
    if obscuring_fog:
        fog_maximum = 255
    else:
        fog_maximum = 205

    key = (path, fog_colour.p, fog_maximum, fog_levels)
    built = palette_cache.get(key)
    if built is None:
        built = []
        for i in range(fog_levels + 1):
            step = i / (fog_levels + 1)
            fog_amount = int(fog_maximum * step)
            built.append(palette(overlay(prop_texture_bank.palette, fog_colour, fog_amount)))
        palette_cache[key] = built
    palettes = built


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


class Entity:
    def __init__(self, x, y, angle, radius):
        self.x = x
        self.y = y
        self.angle = angle
        self.abs_radius = radius
        self.tangible = True

    @property
    @micropython.native
    def grid_pos(self):
        return vec2(int(self.x), int(self.y))

    @property
    @micropython.native
    def pos(self):
        return vec2(self.x, self.y)

    @pos.setter
    @micropython.native
    def pos(self, position):
        self.x = position.x
        self.y = position.y

    @property
    @micropython.native
    def grid_x(self):
        return int(self.x)

    @property
    @micropython.native
    def grid_y(self):
        return int(self.y)

    @property
    @micropython.native
    def vector(self):
        return vec2(math.cos(self.angle), math.sin(self.angle))

    @property
    @micropython.native
    def vector_x(self):
        return math.cos(self.angle)

    @property
    @micropython.native
    def vector_y(self):
        return math.sin(self.angle)

    @property
    @micropython.native
    def radius_x(self):
        return math.copysign(self.abs_radius, self.vector_x)

    @property
    @micropython.native
    def radius_y(self):
        return math.copysign(self.abs_radius, self.vector_y)

    @micropython.native
    def look(self, vector, distance):
        return self.pos + (vector * distance)

    @micropython.native
    def look_ahead(self, distance):
        return self.pos + (self.vector * distance)

    @micropython.native
    def update(self):
        pass


class Prop(Entity):
    def __init__(self, x, y, texture_id, angle=0, radius=0.2):
        super().__init__(x, y, angle, radius)
        self.activatable = False
        self.texture_id = texture_id
        self.tangible = False

    @micropython.native
    def set_texture_palette(self, id):
        prop_texture_bank.palette = palettes[int(id)]

    @micropython.native
    def serve_texture(self, angle):
        final_angle = self.vector.angle_to(angle)
        final_angle += two_pi
        final_angle -= angle_adjust
        if final_angle >= two_pi:
            final_angle -= two_pi
        if final_angle < 0:
            final_angle += two_pi
        rotation_frame = 15 - int((final_angle / two_pi) * 15)
        return prop_texture_bank_sheet.sprite(rotation_frame, self.texture_id)

    @micropython.native
    def update(self):
        pass


class Monster(Entity):
    def __init__(self, filename):
        with open(filename, "r") as file:
            data = file.read()
        x, y, angle, move_speed, turn_speed, radius, height = json.loads(data)
        angle = math.radians(angle)
        super().__init__(x, y, angle, radius)
        self.move_speed = move_speed
        self.turn_speed = turn_speed
        self.height = height
        self.target_pos = self.pos
        self.last_pos = self.pos
        self.update()

    @micropython.native
    def walk(self, current_map, speed=1):
        move_pos = self.look_ahead(self.move_speed * speed)
        current_vel = self.vector * (self.move_speed * speed)

        correction_vector = vec2()
        for entity in entity_list:
            if not entity.tangible:
                continue
            rel_pos = entity.pos - self.pos
            if current_vel.dot(rel_pos) < 0:
                continue
            overlap = (entity.abs_radius + self.abs_radius) - rel_pos.length()
            if overlap <= 0:
                continue

            correction_vector += rel_pos.normalized() * overlap

        adjusted_move_pos = move_pos - correction_vector
        adjusted_velocity = current_vel - correction_vector

        can_move_x = current_map.walkable(vec2(adjusted_move_pos.x + math.copysign(self.abs_radius, adjusted_velocity.x), self.grid_y))
        can_move_y = current_map.walkable(vec2(self.grid_x, adjusted_move_pos.y + math.copysign(self.abs_radius, adjusted_velocity.y)))

        if can_move_x:
            self.x = adjusted_move_pos.x
        if can_move_y:
            self.y = adjusted_move_pos.y

        return can_move_x and can_move_y and correction_vector.length() == 0

    @micropython.native
    def turn(self, turn_rate):
        self.angle += self.turn_speed * turn_rate
        if self.angle < 0:
            self.angle += 2 * math.pi
        if self.angle > 2 * math.pi:
            self.angle -= 2 * math.pi

    @micropython.native
    def grid_roam(self, current_map):
        rel_pos = self.target_pos - self.pos

        if self.turn_to_face(rel_pos):
            if self.walk_to_meet(rel_pos):
                self.set_neighbour_target(current_map)
            else:
                self.walk(current_map)

    def turn_to_face(self, rel_pos):
        target_angle = self.vector.angle_to(rel_pos)
        if abs(target_angle) >= math.pi - self.turn_speed:
            self.turn(random.choice([-1, 1]))
        elif target_angle < 0:
            self.turn(-1)
        elif target_angle > 0:
            self.turn(1)

        if abs(target_angle) <= self.turn_speed:
            self.angle = rel_pos.angle()
            return True

        return False

    def walk_to_meet(self, rel_pos):
        if rel_pos.length() <= self.move_speed:
            self.pos = self.target_pos
            return True
        return False

    def set_neighbour_target(self, level_map):
        neighbours = []
        for grid_offset in (vec2(1, 0), vec2(-1, 0), vec2(0, 1), vec2(0, -1)):
            new_pos = self.pos + grid_offset
            if level_map.walkable(new_pos) and new_pos != self.last_pos:
                neighbours.append(new_pos)
        if len(neighbours) == 0:
            self.target_pos = self.last_pos
            self.last_pos = self.pos
            return
        self.target_pos = random.choice(neighbours)
        self.last_pos = self.pos

    @micropython.native
    def update(self):
        pass
