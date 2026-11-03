"""
Cute Krishna Reveal  -  100% standard library (tkinter only)

No cv2, no numpy, no Pillow: nothing to install. Needs a normal Python 3
with tkinter (included with the python.org installers, so it runs from IDLE).

Run it, then pick a picture in the file dialog, or pass one as an argument:
    python krishna_reveal.py maa-durga.png
Supported pictures: PNG and GIF (convert JPG/BMP/WEBP to PNG first).
Press Esc or Q to quit.
"""

import colorsys
import os
import random
import sys
import time
import tkinter as tk
from itertools import accumulate
from math import gcd
from tkinter import filedialog, messagebox

# --- CONFIGURATION ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
# INPUT_IMAGE is used if the file exists, otherwise a file dialog opens (set it
# to "" to always be asked). A file given on the command line
# (python krishna_reveal.py picture.png) always wins.
INPUT_IMAGE = os.path.join(script_dir, "Durga1.png")

WINDOW_NAME = "Cute Krishna Reveal"
FULLSCREEN = True
WINDOW_W, WINDOW_H = 1280, 720      # only used when FULLSCREEN = False
FPS = 30

DOT_REVEAL_SECONDS = 3.5
REFINE_SECONDS = 3.0
HOLD_SECONDS = 3.0
CROSSFADE_SECONDS = 1.5
FINAL_HOLD_SECONDS = 3.0

MOSAIC_BLOCK_SIZE = 4       # dot size in pixels: smaller = finer + more dots (3 = very fine, slower)
DARK_PIXEL_SKIP = 18        # dots darker than this are not drawn
RANDOM_SEED = 42

EDGE_THRESHOLD = 30         # lower = more outline detail
# Pictures that are already glowing line art on a dark background (like a
# neon drawing) are detected automatically and used as they are, instead of
# running edge detection on them. Use True / False to force it on / off.
LINE_ART_MODE = "auto"
LINE_ART_THRESHOLD = 130    # how bright a block must be to count as a line (lower = thicker glow)
GLOW_STRENGTH = 1.6
REFLECTION_HEIGHT_RATIO = 0.12   # 0 = no reflection
AUTO_CONTRAST = True


class StopShow(Exception):
    """Raised when the user presses Esc / Q or closes the window."""


# --- IMAGE HELPERS ---------------------------------------------------------
def hexc(c):
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def load_photo(path):
    """Load a PNG / GIF picture as a Tk PhotoImage (None if it cannot be read)."""
    try:
        return tk.PhotoImage(file=path)
    except tk.TclError:
        return None


def has_transparency(img):
    try:
        w, h = img.width(), img.height()
        corners = ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))
        return any(img.transparency_get(x, y) for x, y in corners)
    except (tk.TclError, AttributeError):
        return False


def get_pixel(img, x, y, alpha):
    if alpha and img.transparency_get(x, y):
        return (0, 0, 0)
    v = img.get(x, y)
    if isinstance(v, str):
        v = v.split()
    return (int(v[0]), int(v[1]), int(v[2]))


ZOOM_LIMIT = 26_000_000      # max pixels for the temporary zoomed picture


def choose_fraction(iw, ih, ideal):
    """Pick a simple scale n/d (<= ideal) that Tk can apply with zoom + subsample."""
    best = None
    for n in range(1, 9):
        if n > 1 and (iw * n) * (ih * n) > ZOOM_LIMIT:
            break                                 # zoom would use too much memory
        for d in range(1, 17):
            r = n / d
            if r <= ideal + 1e-9 and (best is None or r > best[0]):
                best = (r, n, d)
    if best is None:
        best = (1 / 16, 1, 16)
    _, n, d = best
    g = gcd(n, d)
    return n // g, d // g


def fit_image(raw, n, d):
    """Resize a PhotoImage by the fraction n/d (zoom first keeps the detail)."""
    img = raw
    if n > 1:
        img = img.zoom(n)
    if d > 1:
        img = img.subsample(d)
    return img


def sample_grid(raw, scale, gw, gh, block, alpha, progress):
    """Read one colour per block (the brightest of 4 samples)."""
    iw, ih = raw.width(), raw.height()
    offsets = (0.25, 0.75)
    grid = []
    for gi in range(gh):
        row = []
        for gj in range(gw):
            best, best_sum = (0, 0, 0), -1
            for fy in offsets:
                ry = min(ih - 1, int((gi * block + fy * block) / scale))
                for fx in offsets:
                    rx = min(iw - 1, int((gj * block + fx * block) / scale))
                    c = get_pixel(raw, rx, ry, alpha)
                    s = c[0] + c[1] + c[2]
                    if s > best_sum:
                        best, best_sum = c, s
            row.append(best)
        grid.append(row)
        if gi % 8 == 0:
            progress(gi / gh)
    return grid


def box_blur(chan, gw, gh, r):
    """Fast box blur of a 2D list of floats using running sums."""
    k = 2 * r + 1

    def blur_rows(rows, n):
        out = []
        for row in rows:
            acc = [0.0] + list(accumulate(row))
            out.append([(acc[min(n, j + r + 1)] - acc[max(0, j - r)]) / k
                        for j in range(n)])
        return out

    rows = blur_rows(chan, gw)
    cols = [list(c) for c in zip(*rows)]
    cols = blur_rows(cols, gh)
    return [list(r_) for r_ in zip(*cols)]


def boost(c):
    h, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
    s = min(1.0, s * 1.7)
    v = min(1.0, v * 1.5 + 60 / 255)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return r * 255, g * 255, b * 255


def make_neon(grid, gw, gh, line_art=False):
    """Return (core_grid, neon_grid): glowing outline version of the image."""
    lum = [[0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for c in row] for row in grid]
    chans = [[[0.0] * gw for _ in range(gh)] for _ in range(3)]

    def set_cell(y, x):
        r, g, bl = boost(grid[y][x])
        chans[0][y][x] = r
        chans[1][y][x] = g
        chans[2][y][x] = bl

    if line_art:
        # the picture already is the glowing lines: keep its bright blocks
        for y in range(gh):
            row = lum[y]
            for x in range(gw):
                if row[x] > LINE_ART_THRESHOLD:
                    set_cell(y, x)
    else:
        thr = (EDGE_THRESHOLD * 4) ** 2
        for y in range(1, gh - 1):
            a, b, c = lum[y - 1], lum[y], lum[y + 1]
            for x in range(1, gw - 1):
                gx = (a[x + 1] + 2 * b[x + 1] + c[x + 1]) - (a[x - 1] + 2 * b[x - 1] + c[x - 1])
                gy = (c[x - 1] + 2 * c[x] + c[x + 1]) - (a[x - 1] + 2 * a[x] + a[x + 1])
                if gx * gx + gy * gy > thr:
                    set_cell(y, x)

    inner = [box_blur(ch, gw, gh, 1) for ch in chans]
    outer = [box_blur(box_blur(ch, gw, gh, 2), gw, gh, 2) for ch in chans]

    full = []
    for ci in range(3):
        full.append([[(core * 1.4 + inn * 1.1 + out * 0.7) * GLOW_STRENGTH
                      for core, inn, out in zip(rc, ri, ro)]
                     for rc, ri, ro in zip(chans[ci], inner[ci], outer[ci])])

    k = 1.0
    if AUTO_CONTRAST:
        lit = sorted(v for ch in full for row in ch for v in row if v > 5)
        if lit:
            ref = lit[int(0.99 * (len(lit) - 1))]
            if ref > 1:
                k = 255.0 / ref

    def to_tuples(R, G, B, mult):
        return [[(min(255, int(r * mult)), min(255, int(g * mult)), min(255, int(b * mult)))
                 for r, g, b in zip(rr, gg, bb)]
                for rr, gg, bb in zip(R, G, B)]

    core = to_tuples(*chans, 1.4 * GLOW_STRENGTH * k)
    neon = to_tuples(*full, k)
    return core, neon


def add_reflection(grid, gw, gh):
    refl = int(gh * REFLECTION_HEIGHT_RATIO)
    if refl < 2:
        return grid
    out = list(grid)
    start = gh - refl
    for k in range(refl):
        src = grid[gh - 1 - k]
        fade = 0.35 * (1 - k / (refl - 1))
        dst = grid[start + k]
        out[start + k] = [tuple(max(o, int(0.4 * o + 0.9 * s * fade))
                                for o, s in zip(dp, sp))
                          for dp, sp in zip(dst, src)]
    return out


def blend(a, b, t):
    out = []
    for ra, rb in zip(a, b):
        if ra is rb:
            out.append(ra)
            continue
        out.append([(int(p[0] + (q[0] - p[0]) * t),
                     int(p[1] + (q[1] - p[1]) * t),
                     int(p[2] + (q[2] - p[2]) * t))
                    for p, q in zip(ra, rb)])
    return out


def grid_to_image(grid, gw, gh, zoom):
    """Turn a grid of colours into a Tk image (fast, done inside Tk)."""
    img = tk.PhotoImage(width=gw, height=gh)
    rows = ["{" + " ".join("#%02x%02x%02x" % px for px in row) + "}" for row in grid]
    img.put(" ".join(rows))
    return img.zoom(zoom) if zoom > 1 else img


# --- MAIN ------------------------------------------------------------------
def run_show(root, canvas, W, H, stop, path):
    keep = {}

    def pump():
        root.update()
        if stop["flag"]:
            raise StopShow()

    def run_for(seconds, draw):
        start = time.time()
        while True:
            frame_start = time.time()
            t = min(1.0, (frame_start - start) / seconds) if seconds > 0 else 1.0
            draw(t)
            pump()
            if t >= 1.0:
                break
            time.sleep(max(0.0, 1.0 / FPS - (time.time() - frame_start)))

    status = canvas.create_text(W // 2, H // 2, fill="white", font=("Arial", 20),
                                text="Preparing artwork...")
    pump()

    raw = load_photo(path)
    if raw is None:
        messagebox.showerror(
            WINDOW_NAME,
            "Could not read image:\n%s\n\nUse a PNG or GIF picture "
            "(convert JPG / BMP / WEBP files to PNG first)." % path)
        return

    iw, ih = raw.width(), raw.height()
    frac_n, frac_d = choose_fraction(iw, ih, min(W / iw, H / ih))
    scale = frac_n / frac_d
    block = MOSAIC_BLOCK_SIZE
    gw, gh = int(iw * scale) // block, int(ih * scale) // block
    if gw < 3 or gh < 3:
        messagebox.showerror(WINDOW_NAME, "Image is too small for this block size.")
        return
    ox, oy = (W - gw * block) // 2, (H - gh * block) // 2

    def progress(f):
        canvas.itemconfig(status, text="Preparing artwork... %d%%" % int(f * 80))
        pump()

    alpha = has_transparency(raw)
    original = sample_grid(raw, scale, gw, gh, block, alpha, progress)
    canvas.itemconfig(status, text="Preparing artwork... 90%")
    pump()

    if LINE_ART_MODE == "auto":
        flat = [0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for row in original for c in row]
        line_art = sum(1 for v in flat if v < 25) / len(flat) > 0.7
    else:
        line_art = bool(LINE_ART_MODE)
    core, neon = make_neon(original, gw, gh, line_art)
    core_refl = add_reflection(core, gw, gh)
    neon_refl = add_reflection(neon, gw, gh)
    canvas.delete(status)

    # 1. Dot reveal -----------------------------------------------------------
    dots = [(i, j, c) for i, row in enumerate(core)
            for j, c in enumerate(row) if max(c) > DARK_PIXEL_SKIP]
    random.Random(RANDOM_SEED).shuffle(dots)
    shown = {"n": 0}

    def reveal(t):
        target = int(len(dots) * t)
        for i, j, c in dots[shown["n"]:target]:
            x, y = ox + j * block, oy + i * block
            canvas.create_oval(x, y, x + block, y + block, fill=hexc(c), outline="")
        shown["n"] = target

    run_for(DOT_REVEAL_SECONDS, reveal)

    # 2. Refine: outline sharpens and the glow fades in ----------------------
    canvas.delete("all")
    item = canvas.create_image(ox, oy, anchor="nw")

    def show(grid):
        img = grid_to_image(grid, gw, gh, block)
        canvas.itemconfig(item, image=img)
        keep["img"] = img

    run_for(REFINE_SECONDS, lambda t: show(blend(core_refl, neon_refl, t)))

    # 3. Hold sketch ------------------------------------------------------------
    show(neon_refl)
    run_for(HOLD_SECONDS, lambda t: None)

    # 4. Crossfade to the original colours ------------------------------------
    run_for(CROSSFADE_SECONDS, lambda t: show(blend(neon_refl, original, t)))

    # 5. Final hold with the real picture --------------------------------------
    canvas.delete("all")
    keep["final"] = fit_image(raw, frac_n, frac_d)
    canvas.create_image(W // 2, H // 2, image=keep["final"])
    run_for(FINAL_HOLD_SECONDS, lambda t: None)


def choose_image(root):
    """Command-line argument > INPUT_IMAGE > file dialog."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    if INPUT_IMAGE and os.path.exists(INPUT_IMAGE):
        return INPUT_IMAGE
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Choose a picture",
        filetypes=[("PNG / GIF pictures", "*.png *.gif"),
                   ("All files", "*.*")])
    root.deiconify()
    return path


def main():
    root = tk.Tk()
    root.title(WINDOW_NAME)
    path = choose_image(root)
    if not path:
        root.destroy()
        return
    if FULLSCREEN:
        root.attributes("-fullscreen", True)
        root.update_idletasks()
        W, H = root.winfo_screenwidth(), root.winfo_screenheight()
    else:
        W, H = WINDOW_W, WINDOW_H
        root.geometry("%dx%d" % (W, H))

    canvas = tk.Canvas(root, width=W, height=H, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    stop = {"flag": False}

    def request_stop(event=None):
        stop["flag"] = True

    for key in ("<Escape>", "q", "Q"):
        root.bind(key, request_stop)
    root.protocol("WM_DELETE_WINDOW", request_stop)
    root.focus_force()

    try:
        run_show(root, canvas, W, H, stop, path)
    except (StopShow, tk.TclError):
        pass
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
