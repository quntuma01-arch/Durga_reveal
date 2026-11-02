# Barnsley Fern - auto-scaled to fit the turtle window
from turtle import *
import colorsys
from random import random

bgcolor("black")
title("Barnsley Fern")
setup(0.6, 0.9)     # window = 60% of screen width, 90% of screen height
tracer(0)           # draw off-screen, refresh manually with update()
hideturtle()
penup()

x = 0.0
y = 0.0
h = 0.0

POINTS = 30000

# The fern always stays inside these bounds
FERN_X_MIN, FERN_X_MAX = -2.1820, 2.6558
FERN_Y_MIN, FERN_Y_MAX = 0.0, 9.9983

# Scale the fern so it fills 85% of the window, whatever its size
usable_w = window_width() * 0.85
usable_h = window_height() * 0.85
SCALE = min(usable_w / (FERN_X_MAX - FERN_X_MIN),
            usable_h / (FERN_Y_MAX - FERN_Y_MIN))

# Centre the fern in the window
OFFSET_X = -SCALE * (FERN_X_MIN + FERN_X_MAX) / 2
OFFSET_Y = -SCALE * (FERN_Y_MIN + FERN_Y_MAX) / 2

DOT_SIZE = 2 if SCALE < 60 else 3


def next_point():
    """Apply one of four affine transforms, chosen at random."""
    global x, y
    r = random()
    if r < 0.01:                          # stem
        nx = 0
        ny = 0.16 * y
    elif r < 0.86:                        # smaller and smaller leaflets
        nx = 0.85 * x + 0.04 * y
        ny = -0.04 * x + 0.85 * y + 1.6
    elif r < 0.93:                        # largest left leaflet
        nx = 0.2 * x - 0.26 * y
        ny = 0.23 * x + 0.22 * y + 1.6
    else:                                 # largest right leaflet
        nx = -0.15 * x + 0.28 * y
        ny = 0.26 * x + 0.24 * y + 0.44
    x, y = nx, ny


for i in range(POINTS):
    next_point()
    goto(x * SCALE + OFFSET_X, y * SCALE + OFFSET_Y)
    dot(DOT_SIZE, colorsys.hsv_to_rgb(h % 1.0, 1, 1))
    h += 0.0003
    if i % 1000 == 0:
        update()                          # show the fern growing

update()
done()
