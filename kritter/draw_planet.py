shadow_path = [vec2(35, -36),
               vec2(41, -29),
               vec2(47, -18),
               vec2(50, -5),
               vec2(50, 10),
               vec2(45, 22),
               vec2(39, 32),
               vec2(29, 41),
               vec2(17, 48),
               vec2(5, 50),
               vec2(-6, 50),
               vec2(-16, 48),
               vec2(-26, 43),
               vec2(-35, 36),
               vec2(-43, 26),
               vec2(-32, 32),
               vec2(-15, 35),
               vec2(2, 33),
               vec2(18, 25),
               vec2(30, 14),
               vec2(37, 0),
               vec2(39, -18)]

shadow = shape.custom(shadow_path)

highlight_path = [vec2(9, -33),
                  vec2(2, -14),
                  vec2(-9, -3),
                  vec2(-30, 4),
                  vec2(-37, 1),
                  vec2(-35, -14),
                  vec2(-28, -26),
                  vec2(-14, -34),
                  vec2(2, -37)]

highlight = shape.custom(highlight_path)

planet1_path = [vec2(9, -49),
                vec2(23, -45),
                vec2(35, -36),
                vec2(45, -23),
                vec2(50, -6),
                vec2(49, 9),
                vec2(45, -4),
                vec2(38, -6),
                vec2(19, 6),
                vec2(10, 26),
                vec2(13, 48),
                vec2(-4, 50),
                vec2(-20, 46),
                vec2(-35, 36),
                vec2(-25, 34),
                vec2(-12, 26),
                vec2(-4, 7),
                vec2(-27, 13),
                vec2(-40, 31),
                vec2(-48, 16),
                vec2(-50, -1),
                vec2(-47, -18),
                vec2(-33, -38),
                vec2(-17, -47),
                vec2(-4, -25),
                vec2(32, -13),
                vec2(19, -39)]

planet1 = shape.custom(planet1_path)

planet2_path = [vec2(12, -41),
                vec2(31, -20),
                vec2(15, -18),
                vec2(40, 0),
                vec2(12, -4),
                vec2(-15, -15),
                vec2(-26, -1),
                vec2(-24, 14),
                vec2(-6, 27),
                vec2(-25, 29),
                vec2(-46, 8),
                vec2(-37, -22),
                vec2(-22, -36),
                vec2(-10, -35)]

planet2 = shape.custom(planet2_path)

planet3_path = [vec2(40, -30),
                vec2(31, -36),
                vec2(22, -37),
                vec2(8, -28),
                vec2(3, -8),
                vec2(16, 11),
                vec2(31, 21),
                vec2(43, 14),
                vec2(50, -1),
                vec2(48, 14),
                vec2(44, 24),
                vec2(38, 33),
                vec2(28, 42),
                vec2(15, 48),
                vec2(-2, 50),
                vec2(-17, 47),
                vec2(-30, 40),
                vec2(-15, 43),
                vec2(-8, 38),
                vec2(-2, 21),
                vec2(-12, 4),
                vec2(-30, -9),
                vec2(-44, 6),
                vec2(-44, 24),
                vec2(-49, 11),
                vec2(-50, -4),
                vec2(-47, -18),
                vec2(-40, -30),
                vec2(-33, -38),
                vec2(-22, -45),
                vec2(-11, -49),
                vec2(6, -50),
                vec2(21, -46),
                vec2(31, -40)]

planet3 = shape.custom(planet3_path)

planet4_path = [vec2(-9, -49),
                vec2(6, -50),
                vec2(21, -46),
                vec2(33, -37),
                vec2(46, -21),
                vec2(49, -8),
                vec2(41, -17),
                vec2(36, -4),
                vec2(34, 15),
                vec2(46, 20),
                vec2(36, 35),
                vec2(25, 43),
                vec2(10, 49),
                vec2(19, 37),
                vec2(21, 23),
                vec2(13, 11),
                vec2(-4, 27),
                vec2(-20, 29),
                vec2(-17, 16),
                vec2(-22, -3),
                vec2(-37, -12),
                vec2(-50, -5),
                vec2(-46, -19),
                vec2(-39, -32),
                vec2(-38, -25),
                vec2(-3, -20),
                vec2(20, -11),
                vec2(18, -34),
                vec2(7, -42)]

planet4 = shape.custom(planet4_path)

planet5_path = [vec2(31, -28),
                vec2(31, -20),
                vec2(40, -14),
                vec2(41, 16),
                vec2(-8, 35),
                vec2(-39, 16),
                vec2(-34, -4),
                vec2(-11, -6),
                vec2(4, 16),
                vec2(35, 11),
                vec2(29, -11),
                vec2(15, -12),
                vec2(0, -21),
                vec2(-7, -30),
                vec2(0, -38),
                vec2(15, -38)]

planet5 = shape.custom(planet5_path)

patterns = [planet1, planet2, planet3, planet4, planet5]
planet_bg = shape.circle(vec2(0, 0), 50)


def draw_planet(planet):
    r, g, b = planet.colour
    dark_factor = 0.75
    scale_factor = 0.02 * planet.radius

    light_colour = color.rgb(r, g, b)
    dark_colour = color.rgb(r * dark_factor, g * dark_factor, b * dark_factor)

    transformation = mat3().translate(planet.pos.x, planet.pos.y).scale(scale_factor).rotate(planet.rotation)
    shadow_transformation = mat3().translate(planet.pos.x, planet.pos.y).scale(scale_factor)

    screen.pen = light_colour
    planet_bg.transform = transformation
    screen.shape(planet_bg)

    screen.pen = dark_colour
    pattern = patterns[planet.pattern]
    pattern.transform = transformation
    screen.shape(pattern)

    screen.pen = color.rgb(0, 0, 0, 128)
    shadow.transform = shadow_transformation
    screen.shape(shadow)

    screen.pen = color.rgb(255, 255, 255, 64)
    highlight.transform = shadow_transformation
    screen.shape(highlight)
