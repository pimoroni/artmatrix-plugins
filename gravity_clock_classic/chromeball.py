sphere_bg = shape.circle(vec2(0, 0), 50)
highlight1 = shape.custom([vec2(-4, -46), vec2(15, -43), vec2(31, -30), vec2(19, -29), vec2(4, -35), vec2(-18, -31), vec2(-23, -36), vec2(-20, -40)])
highlight2 = shape.custom([vec2(-10, -29), vec2(13, -28), vec2(8, -5), vec2(-10, -6)])
highlight3 = shape.custom([vec2(-28, -37), vec2(-29, -26), vec2(-25, -18), vec2(-31, -11), vec2(-39, -15), vec2(-37, -28)])
highlight4 = shape.custom([vec2(48, -5), vec2(49, -2), vec2(49, 4), vec2(44, 14), vec2(26, 23), vec2(-3, 27), vec2(-27, 26), vec2(-44, 20), vec2(-50, 8), vec2(-49, 10), vec2(-44, 4), vec2(-26, 11), vec2(4, 14), vec2(26, 12), vec2(44, 4)])
shadow1 = shape.custom([vec2(41, -25), vec2(47, -9), vec2(42, 2), vec2(25, 9), vec2(2, 11), vec2(-27, 7), vec2(-42, 1), vec2(-48, -12), vec2(-41, -28), vec2(-44, -12), vec2(-30, -6), vec2(-20, -13), vec2(-12, -1), vec2(12, -1), vec2(14, -13), vec2(30, -17), vec2(43, -12)])
shadow2 = shape.custom([vec2(36, 33), vec2(20, 45), vec2(0, 50), vec2(-19, 46), vec2(-37, 34), vec2(-21, 41), vec2(0, 35), vec2(22, 40)])


@micropython.native
def draw_ball(pos, radius, colour_values):
    x = pos.x / 100
    y = pos.y / 100

    transformation = mat3().translate(x, y).scale(0.0002 * radius).rotate(315)

    r, g, b = colour_values
    colour = color.rgb(r, g, b)
    dark_colour = color.rgb(r / 2, g / 2, b / 2)

    screen.pen = colour
    sphere_bg.transform = transformation
    screen.shape(sphere_bg)

    screen.pen = color.white
    highlight1.transform = transformation
    highlight2.transform = transformation
    highlight3.transform = transformation
    highlight4.transform = transformation
    screen.shape(highlight1)
    screen.shape(highlight2)
    screen.shape(highlight3)
    screen.shape(highlight4)

    screen.pen = dark_colour
    shadow1.transform = transformation
    shadow2.transform = transformation
    screen.shape(shadow1)
    screen.shape(shadow2)
