#!/usr/bin/env python3
"""THE WORLD IN ONE DAY - Saturday 21 November 2026.

A deterministic, offline, standard-library-only program that draws a
broadsheet front page summing up the world's news of 21 November 2026
and writes it to /output/entry.png (1024x1024 PNG, under 1 MiB).

Every story was reported on 21 November 2026 by the named source; the
figures are the sources' own. Rendering is done at 2x and box-downsampled
so small text stays crisp. No network, no randomness, no clock.
"""

import os
import struct
import zlib

# ---------------------------------------------------------------- PNG writer

def png_bytes(width, height, rgb):
    """rgb: bytearray of width*height*3. Returns a complete PNG file."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", idat) + chunk(b"IEND", b""))

# ---------------------------------------------------------------- canvas

SS = 2                      # supersample factor
W, H = 1024, 1024           # final size
CW, CH = W * SS, H * SS     # canvas size

class Canvas:
    def __init__(self):
        self.px = bytearray(CW * CH * 3)

    def set(self, x, y, col):
        if 0 <= x < CW and 0 <= y < CH:
            i = (y * CW + x) * 3
            self.px[i:i + 3] = bytes(col)

    def rect(self, x, y, w, h, col):
        x, y, w, h = int(x * SS), int(y * SS), int(w * SS), int(h * SS)
        if w <= 0 or h <= 0:
            return
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, CW), min(y + h, CH)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(col) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * CW + x0) * 3
            self.px[i:i + len(row)] = row

    def hline(self, x, y, w, col, t=1):
        self.rect(x, y, w, t, col)

    def vline(self, x, y, h, col, t=1):
        self.rect(x, y, t, h, col)

    def frame(self, x, y, w, h, col, t=1):
        self.hline(x, y, w, col, t)
        self.hline(x, y + h - t, w, col, t)
        self.vline(x, y, h, col, t)
        self.vline(x + w - t, y, h, col, t)

    def disc(self, cx, cy, r, col):
        cx, cy, r = cx * SS, cy * SS, r * SS
        x0, x1 = int(cx - r), int(cx + r)
        y0, y1 = int(cy - r), int(cy + r)
        for yy in range(max(y0, 0), min(y1, CH - 1) + 1):
            for xx in range(max(x0, 0), min(x1, CW - 1) + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.set(xx, yy, col)

    def ring(self, cx, cy, r, col, t=2):
        cx, cy, r = cx * SS, cy * SS, r * SS
        tt = t * SS
        x0, x1 = int(cx - r - tt), int(cx + r + tt)
        y0, y1 = int(cy - r - tt), int(cy + r + tt)
        for yy in range(max(y0, 0), min(y1, CH - 1) + 1):
            for xx in range(max(x0, 0), min(x1, CW - 1) + 1):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if (r - tt) ** 2 <= d2 <= (r + tt) ** 2:
                    self.set(xx, yy, col)

    def line(self, x0, y0, x1, y1, col, t=2):
        """Thick line via dense disc stamps along the segment."""
        import math
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist * 2))
        for i in range(steps + 1):
            f = i / steps
            self.disc(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, t / 2.0, col)

    def poly(self, pts, col):
        """Filled polygon, points in final-image coordinates."""
        import math
        sp = [(x * SS, y * SS) for x, y in pts]
        ys = [p[1] for p in sp]
        y0, y1 = max(int(min(ys)), 0), min(int(max(ys)), CH - 1)
        n = len(sp)
        for yy in range(y0, y1 + 1):
            nodes = []
            for i in range(n):
                xa, ya = sp[i]
                xb, yb = sp[(i + 1) % n]
                if (ya <= yy < yb) or (yb <= yy < ya):
                    nodes.append(xa + (yy - ya) * (xb - xa) / (yb - ya))
            nodes.sort()
            for i in range(0, len(nodes) - 1, 2):
                xa, xb = int(nodes[i]), int(nodes[i + 1])
                for xx in range(max(xa, 0), min(xb, CW - 1) + 1):
                    self.set(xx, yy, col)

    def downsample(self):
        out = bytearray(W * H * 3)
        for y in range(H):
            for x in range(W):
                r = g = b = 0
                for dy in range(SS):
                    base = ((y * SS + dy) * CW + x * SS) * 3
                    for dx in range(SS):
                        i = base + dx * 3
                        r += self.px[i]; g += self.px[i + 1]; b += self.px[i + 2]
                o = (y * W + x) * 3
                n = SS * SS
                out[o] = r // n; out[o + 1] = g // n; out[o + 2] = b // n
        return out

# ---------------------------------------------------------------- 5x7 font
# Each glyph: 7 rows of 5 pixels, '#' = ink. Uppercase set + digits + marks.

FONT = {
"A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
"B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
"C": [" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"],
"D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
"E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
"F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
"G": [" ####", "#    ", "#    ", "#  ##", "#   #", "#   #", " ### "],
"H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
"I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
"J": ["#####", "    #", "    #", "    #", "    #", "#   #", " ### "],
"K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
"L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
"M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
"N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
"O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
"P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
"Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
"R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
"S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
"T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
"U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
"V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
"W": ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
"X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
"Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
"Z": ["#####", "    #", "   #  ", "  #   ", " #    ", "#    ", "#####"],
"0": [" ### ", "#  ##", "# # #", "##  #", "#   #", "#   #", " ### "],
"1": ["  #  ", " ##  ", "# #  ", "  #  ", "  #  ", "  #  ", "#####"],
"2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
"3": ["#### ", "    #", "    #", " ### ", "    #", "    #", "#### "],
"4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
"5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
"6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
"7": ["#####", "    #", "   # ", "   # ", "  #  ", "  #  ", "  #  "],
"8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
"9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
".": ["     ", "     ", "     ", "     ", "     ", "     ", " ##  "],
",": ["     ", "     ", "     ", "     ", "     ", " ##  ", "##   "],
"'": ["  #  ", "  #  ", " #   ", "     ", "     ", "     ", "     "],
":": ["     ", " ##  ", " ##  ", "     ", " ##  ", " ##  ", "     "],
";": ["     ", " ##  ", " ##  ", "     ", " ##  ", " ##  ", "##   "],
"!": ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
"?": [" ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  "],
"-": ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
"/": ["    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "],
"(": ["   ##", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   ##"],
")": ["##   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", "##   "],
"$": ["  #  ", " ####", "# #  ", " ### ", "  # #", "#### ", "  #  "],
"%": ["##  #", "## # ", "    #", "   # ", "  #  ", " # ##", "#  ##"],
"+": ["     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "],
"=": ["     ", "     ", "#####", "     ", "#####", "     ", "     "],
"&": [" ##  ", "#  # ", "# #  ", " #   ", "# # #", "#  # ", " ## #"],
"*": ["     ", "# # #", " ### ", "#####", " ### ", "# # #", "     "],
"#": [" # # ", " # # ", "#####", " # # ", "#####", " # # ", " # # "],
'"': [" # # ", " # # ", " # # ", "     ", "     ", "     ", "     "],
"<": ["    #", "   # ", "  #  ", " #   ", "  #  ", "   # ", "    #"],
">": ["#    ", " #   ", "  #  ", "   # ", "  #  ", " #   ", "#    "],
"_": ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
"~": ["     ", "     ", "     ", " ## #", "# ## ", "     ", "     "],
" ": ["     ", "     ", "     ", "     ", "     ", "     ", "     "],
}

def text_w(s, scale):
    """Width in final-image px of string s at the given scale (px per font px)."""
    return len(s) * 6 * scale - scale

def draw_text(cv, x, y, s, col, scale=2, bold=False):
    """Draw s with its top-left at (x, y) in final-image coordinates.
    scale = final px per font pixel. Returns the x just past the text."""
    s = s.upper()
    cx = x
    for ch in s:
        glyph = FONT.get(ch, FONT[" "])
        for gy, row in enumerate(glyph):
            for gx, cell in enumerate(row):
                if cell == "#":
                    cv.rect(cx + gx * scale, y + gy * scale, scale, scale, col)
                    if bold:
                        cv.rect(cx + gx * scale + scale * 0.5, y + gy * scale,
                                scale, scale, col)
        cx += 6 * scale
    return cx - scale

def wrap(s, scale, max_w):
    """Greedy word wrap: returns list of lines fitting max_w final px."""
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        trial = wd if not cur else cur + " " + wd
        if text_w(trial, scale) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines

def draw_wrapped(cv, x, y, s, col, scale, max_w, line_h, max_lines=None):
    lines = wrap(s, scale, max_w)
    if max_lines is not None:
        lines = lines[:max_lines]
    for i, ln in enumerate(lines):
        draw_text(cv, x, y + i * line_h, ln, col, scale)
    return y + len(lines) * line_h

# ---------------------------------------------------------------- palette

PAPER = (246, 241, 230)
INK = (24, 24, 32)
RED = (178, 34, 40)
BLUE = (28, 62, 110)
TEAL = (18, 110, 104)
GOLD = (196, 144, 32)
GREY = (96, 96, 104)
LGREY = (214, 208, 194)
WHITE = (252, 250, 244)
DARK = (18, 22, 38)
SKY = (196, 220, 238)
LAND = (168, 188, 152)
SEA = (172, 205, 226)

# ---------------------------------------------------------------- world map
# Coarse continent outlines as (lon, lat) polygons, drawn on a true
# equirectangular projection: x from lon, y from lat, nothing eyeballed.

CONTINENTS = [
    # North America
    [(-168, 66), (-140, 70), (-125, 72), (-110, 73), (-95, 80), (-85, 70),
     (-80, 73), (-75, 72), (-65, 62), (-55, 52), (-65, 45), (-70, 42),
     (-74, 40), (-76, 35), (-80, 32), (-80, 26), (-84, 30), (-90, 29),
     (-97, 26), (-97, 22), (-94, 17), (-87, 13), (-83, 9), (-79, 9),
     (-86, 13), (-92, 15), (-97, 16), (-105, 20), (-110, 23), (-114, 29),
     (-117, 33), (-122, 37), (-124, 46), (-130, 55), (-150, 60), (-165, 60)],
    # Greenland
    [(-45, 60), (-30, 68), (-22, 70), (-20, 76), (-30, 82), (-55, 80),
     (-58, 72), (-53, 64)],
    # South America
    [(-79, 9), (-72, 12), (-62, 10), (-50, 0), (-44, -3), (-35, -8),
     (-39, -13), (-40, -22), (-48, -27), (-52, -33), (-58, -39), (-62, -41),
     (-65, -45), (-67, -50), (-68, -54), (-71, -54), (-73, -46), (-73, -37),
     (-71, -30), (-70, -20), (-75, -15), (-79, -8), (-81, -4), (-80, 1),
     (-77, 4)],
    # Africa
    [(-6, 35), (0, 36), (10, 37), (11, 34), (20, 32), (30, 31), (32, 31),
     (35, 28), (38, 22), (40, 15), (43, 12), (48, 11), (51, 12), (48, 5),
     (42, -2), (40, -10), (38, -18), (36, -22), (33, -26), (28, -33),
     (20, -35), (17, -32), (15, -27), (13, -18), (12, -10), (9, -2),
     (9, 4), (-8, 4), (-13, 8), (-17, 15), (-16, 20), (-15, 25),
     (-13, 28), (-10, 31)],
    # Madagascar
    [(44, -16), (47, -15), (50, -18), (48, -22), (46, -25), (44, -24),
     (43, -20), (44, -17)],
    # Eurasia
    [(-9, 43), (-9, 48), (-2, 50), (0, 52), (5, 53), (8, 55), (10, 58),
     (18, 60), (22, 64), (28, 68), (35, 65), (45, 66), (55, 68), (68, 69),
     (80, 70), (95, 72), (110, 74), (125, 73), (140, 72), (155, 70),
     (170, 67), (178, 66), (178, 62), (162, 60), (158, 52), (150, 45),
     (142, 42), (140, 38), (135, 35), (129, 33), (126, 34), (122, 31),
     (120, 25), (115, 23), (108, 18), (106, 9), (103, 2), (100, 7),
     (98, 12), (94, 17), (91, 22), (88, 22), (86, 20), (80, 15), (77, 8),
     (74, 12), (72, 20), (68, 23), (66, 25), (61, 25), (57, 26), (52, 26),
     (50, 29), (48, 30), (50, 25), (55, 24), (58, 22), (55, 17), (52, 15),
     (45, 12), (43, 12), (40, 15), (38, 20), (36, 28), (34, 28), (36, 33),
     (36, 36), (30, 36), (27, 37), (23, 36), (19, 40), (15, 38), (12, 44),
     (8, 44), (3, 42), (0, 39), (-2, 37), (-6, 36), (-9, 37)],
    # Britain
    [(-5, 50), (-3, 53), (-5, 56), (-3, 58), (-1, 57), (-2, 54), (-1, 52),
     (-3, 50)],
    # Japan
    [(130, 31), (133, 34), (137, 35), (140, 36), (141, 40), (142, 44),
     (140, 45), (138, 38), (135, 34), (131, 32)],
    # Sumatra
    [(95, 5), (100, 0), (104, -3), (106, -6), (103, -4), (99, 1), (96, 4)],
    # Borneo
    [(109, 1), (113, 3), (117, 5), (119, 1), (117, -2), (113, -3),
     (110, -2)],
    # Java
    [(106, -6), (110, -7), (114, -8), (114, -9), (108, -8), (106, -7)],
    # New Guinea
    [(131, -1), (136, -2), (141, -3), (146, -6), (150, -9), (147, -9),
     (142, -8), (137, -7), (132, -4)],
    # Australia
    [(114, -22), (113, -26), (115, -32), (118, -35), (124, -33), (129, -32),
     (132, -32), (135, -35), (138, -35), (140, -38), (145, -38), (150, -37),
     (153, -31), (153, -27), (151, -24), (146, -19), (142, -15), (142, -11),
     (140, -17), (136, -15), (135, -12), (132, -11), (130, -13), (126, -14),
     (122, -17), (118, -20)],
    # New Zealand
    [(167, -45), (170, -43), (172, -41), (174, -39), (176, -38), (174, -41),
     (171, -44), (168, -46)],
]

MAP_X, MAP_Y, MAP_W, MAP_H = 24, 464, 976, 168
LON0, LON1 = -180, 180
LAT0, LAT1 = 82, -58          # top, bottom

def project(lon, lat):
    x = MAP_X + (lon - LON0) / (LON1 - LON0) * MAP_W
    y = MAP_Y + (LAT0 - lat) / (LAT0 - LAT1) * MAP_H
    return x, y

# (number, lon, lat, badge offset dx, dy)
PINS = [
    (1, -74.0, 40.7, -16, -14),     # New York
    (2, 30.7, 36.9, 12, 10),        # Antalya
    (3, 46.7, 24.6, 12, 8),         # Riyadh
    (4, 30.5, 50.4, 14, -6),        # Kyiv
    (5, 13.4, 52.5, -4, 14),        # Berlin
    (6, 12.6, 55.7, -16, -12),      # Copenhagen
    (7, -118.2, 34.1, -14, -12),    # Los Angeles
    (8, 28.0, -26.2, 12, 6),        # Johannesburg
    (9, 127.0, 37.6, 12, -8),       # Seoul
    (10, 2.35, 48.9, -18, 8),       # Paris
    (11, 4.5, 52.1, -20, -14),      # The Hague
    (12, 21.0, 52.2, 16, -14),      # Warsaw
    (13, 44.4, 33.3, 14, -10),      # Baghdad
    (14, 77.2, 28.6, 12, -8),       # New Delhi
    (15, 24.7, 59.4, 10, -16),      # Tallinn
    (16, 38.8, 9.0, 12, 8),         # Addis Ababa
    (17, -77.0, 38.9, 14, 12),      # Washington DC
    (18, -122.0, 37.4, -18, 12),    # San Francisco Bay Area
]

def draw_map(cv):
    cv.rect(MAP_X, MAP_Y, MAP_W, MAP_H, SEA)
    cv.frame(MAP_X, MAP_Y, MAP_W, MAP_H, INK, 1)
    for poly in CONTINENTS:
        cv.poly([project(lon, lat) for lon, lat in poly], LAND)
    for num, lon, lat, dx, dy in PINS:
        x, y = project(lon, lat)
        bx, by = x + dx, y + dy
        cv.line(x, y, bx, by, RED, 1)
        cv.disc(x, y, 2.2, RED)
        cv.disc(bx, by, 6.5, RED)
        label = str(num)
        tw = text_w(label, 1.1)
        draw_text(cv, bx - tw / 2, by - 3.8, label, WHITE, 1.1, bold=True)

# ---------------------------------------------------------------- lead art

def ill_markets(cv, x, y, w, h):
    cv.rect(x, y, w, h, DARK)
    for i in range(1, 5):                       # grid
        gy = y + h * i / 5
        cv.hline(x + 6, gy, w - 12, (52, 60, 88), 1)
    for i in range(1, 7):
        gx = x + w * i / 7
        cv.vline(gx, y + 5, h - 10, (52, 60, 88), 1)
    pts = [(x + w * f, y + h * g) for f, g in
           [(0.03, 0.22), (0.16, 0.16), (0.28, 0.30), (0.40, 0.26),
            (0.52, 0.44), (0.64, 0.40), (0.76, 0.62), (0.88, 0.58),
            (0.97, 0.82)]]
    for a, b in zip(pts, pts[1:]):
        cv.line(a[0], a[1], b[0], b[1], (240, 90, 80), 3)
    ex, ey = pts[-1]                            # arrowhead
    cv.poly([(ex, ey), (ex - 13, ey - 3), (ex - 4, ey - 12)], (240, 90, 80))
    for f, top, bot in [(0.10, 0.30, 0.48), (0.34, 0.38, 0.55),
                        (0.58, 0.52, 0.68), (0.82, 0.66, 0.86)]:
        cv.rect(x + w * f, y + h * top, 9, h * (bot - top), GOLD)

def ill_climate(cv, x, y, w, h):
    cv.rect(x, y, w, h, SKY)
    cv.disc(x + w - 34, y + 24, 13, GOLD)       # sun
    for dx in (-18, 0, 18):                     # rays
        cv.line(x + w - 34 + dx * 0.6, y + 24 - 14, x + w - 34 + dx, y + 24 - 22,
                GOLD, 2)
    base = y + h - 16                           # conference hall
    cv.rect(x + 26, base - 34, w - 90, 34, WHITE)
    cv.frame(x + 26, base - 34, w - 90, 34, INK, 1)
    import math
    for i in range(41):                         # dome
        f = i / 40
        dx = (f - 0.5) * (w - 90)
        dy = -math.sin(f * math.pi) * 30
        cv.disc(x + 26 + (w - 90) / 2 + dx, base - 34 + dy, 2.2, BLUE)
    for i in range(5):                          # columns
        cx = x + 40 + i * (w - 118) / 4
        cv.rect(cx, base - 30, 5, 26, BLUE)
    tx = x + w - 44                             # thermometer
    cv.rect(tx, y + 14, 9, h - 44, WHITE)
    cv.frame(tx, y + 14, 9, h - 44, INK, 1)
    cv.rect(tx + 2, y + 26, 5, h - 56, RED)
    cv.disc(tx + 4.5, y + h - 22, 9, RED)

def ill_riyadh(cv, x, y, w, h):
    cv.rect(x, y, w, h, (16, 20, 44))
    for i in range(36):                         # stars (fixed pattern)
        sx = x + (i * 53 % 97) / 97 * w
        sy = y + (i * 31 % 43) / 43 * h * 0.5
        cv.rect(sx, sy, 1.6, 1.6, (220, 226, 240))
    base = y + h
    for bx, bw, bh in [(0.02, 0.10, 0.34), (0.14, 0.07, 0.48), (0.23, 0.09, 0.30),
                       (0.34, 0.06, 0.55), (0.42, 0.10, 0.38), (0.55, 0.07, 0.44),
                       (0.64, 0.09, 0.30), (0.75, 0.06, 0.50), (0.83, 0.09, 0.36),
                       (0.94, 0.05, 0.42)]:
        cv.rect(x + w * bx, base - h * bh, w * bw, h * bh, (34, 42, 74))
    import math
    for sx, ex, peak in [(0.08, 0.52, 0.72), (0.30, 0.74, 0.84), (0.55, 0.95, 0.66)]:
        for i in range(31):                    # interceptor arcs
            f = i / 30
            ax = x + w * (sx + (ex - sx) * f)
            ay = base - math.sin(f * math.pi) * h * peak
            cv.disc(ax, ay, 1.8, GOLD)
        cv.disc(x + w * ex, base - 2, 3.5, (240, 120, 70))

# ---------------------------------------------------------------- icons
# Chunky padded icons drawn inside a 36x36 box at (x, y).

def icon_quote(cv, x, y, col):
    cv.rect(x + 4, y + 8, 12, 10, col)
    cv.poly([(x + 8, y + 18), (x + 16, y + 18), (x + 9, y + 27)], col)
    cv.rect(x + 20, y + 8, 12, 10, col)
    cv.poly([(x + 24, y + 18), (x + 32, y + 18), (x + 25, y + 27)], col)

def icon_crowd(cv, x, y, col):
    for cx, cy, r in [(12, 14, 5), (24, 14, 5), (18, 11, 5.5)]:
        cv.disc(x + cx, y + cy, r, col)
    cv.poly([(x + 4, y + 32), (x + 14, y + 20), (x + 22, y + 20),
             (x + 32, y + 32)], col)

def icon_flame(cv, x, y, col):
    cv.poly([(x + 18, y + 3), (x + 24, y + 13), (x + 28, y + 18),
             (x + 27, y + 27), (x + 22, y + 33), (x + 14, y + 33),
             (x + 9, y + 27), (x + 8, y + 18), (x + 12, y + 12)], col)
    cv.poly([(x + 18, y + 16), (x + 22, y + 23), (x + 21, y + 29),
             (x + 15, y + 29), (x + 14, y + 23)], GOLD)

def icon_stamp(cv, x, y, col):
    cv.frame(x + 6, y + 5, 24, 27, col, 3)
    cv.disc(x + 18, y + 15, 6, col)
    cv.hline(x + 11, y + 26, 14, col, 3)

def icon_bars(cv, x, y, col):
    for i in range(4):
        cv.rect(x + 6 + i * 7, y + 6, 4, 24, col)
    cv.hline(x + 4, y + 4, 28, col, 3)
    cv.hline(x + 4, y + 30, 28, col, 3)

def icon_ballot(cv, x, y, col):
    cv.rect(x + 5, y + 14, 26, 16, col)
    cv.rect(x + 12, y + 5, 12, 10, col)
    cv.rect(x + 15, y + 8, 6, 4, PAPER)

def icon_scale(cv, x, y, col):
    cv.vline(x + 17, y + 5, 24, col, 3)
    cv.hline(x + 6, y + 8, 24, col, 3)
    cv.poly([(x + 2, y + 20), (x + 10, y + 20), (x + 6, y + 12)], col)
    cv.poly([(x + 26, y + 20), (x + 34, y + 20), (x + 30, y + 12)], col)
    cv.hline(x + 10, y + 31, 16, col, 3)

def icon_chip(cv, x, y, col):
    cv.rect(x + 9, y + 9, 18, 18, col)
    cv.rect(x + 14, y + 14, 8, 8, PAPER)
    for i in range(3):
        cv.vline(x + 12 + i * 6, y + 3, 6, col, 2)
        cv.vline(x + 12 + i * 6, y + 27, 6, col, 2)
        cv.hline(x + 3, y + 12 + i * 6, 6, col, 2)
        cv.hline(x + 27, y + 12 + i * 6, 6, col, 2)

def icon_star(cv, x, y, col):
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = 15 if i % 2 == 0 else 6.5
        pts.append((x + 18 + r * math.cos(ang), y + 18 + r * math.sin(ang)))
    cv.poly(pts, col)

def icon_badge(cv, x, y, col):
    cv.poly([(x + 18, y + 3), (x + 30, y + 7), (x + 30, y + 18),
             (x + 18, y + 33), (x + 6, y + 18), (x + 6, y + 7)], col)
    cv.disc(x + 18, y + 16, 5.5, PAPER)

ICONS = [icon_quote, icon_crowd, icon_flame, icon_stamp, icon_bars,
         icon_ballot, icon_scale, icon_chip, icon_star, icon_badge]

# ---------------------------------------------------------------- content

STATS = [
    ("-10%", "NASDAQ'S WEEK - WORST SINCE MARCH 2020 (WSJ)"),
    ("$4TN+", "WIPED OFF THE NASDAQ'S VALUE THIS WEEK (WSJ)"),
    ("-8.5%", "ANTHROPIC FRIDAY, $88.91 VS $83 IPO PRICE (CNN)"),
    ("~200", "COUNTRIES DEADLOCKED AT COP31, ANTALYA (AP)"),
    ("3", "HOUTHI MISSILES INTERCEPTED OVER SAUDI (AJ)"),
    ("25", "EUROPEAN COUNTRIES IN GEN Z PROTESTS (AJ)"),
]

LEADS = [
    ("MARKETS - LEAD STORY", ill_markets,
     "AI ROUT: NASDAQ'S WORST WEEK SINCE 2020",
     "THE NASDAQ FELL 5.3% FRIDAY, 10% ON THE WEEK - OVER $4 TRILLION GONE "
     "(WSJ). ANTHROPIC SLID 8.5% TO $88.91, BARELY ABOVE ITS $83 IPO PRICE "
     "(CNN); NVIDIA DROPPED 14% FRIDAY (WSJ). ASIA'S MARKETS DIVED (AJ)."),
    ("CLIMATE - LEAD STORY", ill_climate,
     "COP31 RUNS INTO OVERTIME WITH NO DEAL",
     "NEARLY 200 COUNTRIES STILL DEADLOCKED IN ANTALYA ON SATURDAY. THE "
     "LATEST DRAFT DROPS ALL MENTION OF FOSSIL FUELS AND THE $120BN-A-YEAR "
     "ADAPTATION TARGET; A THIRD DRAFT WAS PROMISED FOR SATURDAY (AP)."),
    ("MIDDLE EAST - LEAD STORY", ill_riyadh,
     "THIRD NIGHT OF MISSILES OVER RIYADH",
     "THE SAUDI-LED COALITION SAID IT INTERCEPTED THREE HOUTHI MISSILES. "
     "IRAN'S IRGC CLAIMED IT DOWNED A US MQ-9 DRONE OVER THE STRAIT OF "
     "HORMUZ (AL JAZEERA)."),
]

FEATURES = [
    ("ZELENSKY: 'A KILLER'",
     "TRUMP CALLED PUTIN HIS 'FRIEND'; ZELENSKY TOLD CNN: 'FOR US, HE IS A "
     "KILLER' (BBC)."),
    ("GEN Z PROTESTS, 25 COUNTRIES",
     "THOUSANDS RALLIED ACROSS EUROPE OVER COSTS, WAR SPENDING AND CLIMATE "
     "(AJ)."),
    ("PALISADES ARSONIST GUILTY",
     "A 30-YEAR-OLD CONVICTED OVER THE FIRE THAT KILLED 12, BURNED 6,800+ "
     "BUILDINGS (BBC)."),
    ("DENMARK EXPELS DIPLOMAT",
     "A RUSSIAN DIPLOMAT EXPELLED OVER AN ALLEGED PLOT TO KILL A US-UKRAINIAN "
     "RAPPER (AJ)."),
    ("RIKERS TO CLOSE BY 2032",
     "MAYOR MAMDANI UNVEILS A PLAN TO SHUT NEW YORK'S RIKERS ISLAND JAIL "
     "COMPLEX (BBC)."),
    ("ANC FIGHTS FOR THE CITIES",
     "THE ANC FIGHTS TO HOLD SOUTH AFRICA'S KEY CITIES AFTER A LOCAL "
     "ELECTION SETBACK (BBC)."),
    ("$811M BAIL-BOND FRAUD",
     "US FIRMS FINED $811M FOR CONNING DETAINED MIGRANTS - AND THE SCAMS "
     "WENT ON (BBC)."),
    ("TRUMP: BRING BACK HUANG",
     "TRUMP URGES NVIDIA TO REINSTATE CEO JENSEN HUANG WITH A 'BIG APOLOGY' "
     "(AJ)."),
    ("AFRICA'S OWN RATING AGENCY",
     "A NEW AFRICAN CREDIT RATER LAUNCHES TO CHALLENGE THE GLOBAL AGENCIES "
     "(AJ)."),
    ("ZECLER OFFICERS SENTENCED",
     "3 FRENCH OFFICERS SENTENCED OVER THE RACIST ASSAULT ON MICHEL ZECLER "
     "(BBC)."),
]

BRIEFS = [
    "MYANMAR AND CHINA OBJECT TO THE ICJ ROHINGYA GENOCIDE RULING (AJ)",
    "NATO CHIEF RUTTE DUE IN WARSAW AFTER MISSILES FELL IN POLAND (AP)",
    "IRAQI FORCES DEPLOY TO JURF AL-SAKHAR AFTER MILITIA DEAL (AJ)",
    "TRUMP THREATENS TAX ON US FIRMS BUILDING AI DATA CENTRES ABROAD (AJ)",
    "111 SUNEUNG CANDIDATES FOUND WITH BANNED SMART DEVICES (BBC)",
    "NEARLY 600 WOMEN KILLED IN SOUTH AFRICA IN THREE MONTHS (BBC)",
    "INDIAN MAN GETS 19+ YEARS IN US OVER SIKH SEPARATIST PLOT (BBC)",
    "NIGERIA MOVES TO END JAIL TERMS FOR ATTEMPTED SUICIDE (BBC)",
    "JUDGE APPROVES $7.25BN ROUNDUP CANCER SETTLEMENT (BBC)",
    "TEXAS EXECUTION TOOK MORE THAN AN HOUR, WITNESSES SAY (BBC)",
    "US DECLASSIFIES MORE UFO FOOTAGE FROM THE MIDDLE EAST (BBC)",
    "NEPAL PM SHAH BEGINS FIRST INDIA VISIT; TRADE TOPS AGENDA (BBC)",
    "PAKISTAN GUARD OF HONOUR FOR INDIA AFTER SAFF FINAL LOSS (AJ)",
    "POCHETTINO TAKES OVER AT MAN UTD; FIRST GAME SUNDAY (AJ)",
    "RUSSIA CRIES 'IRON CURTAIN' AS ESTONIA SHUTS ITS BORDERS (AJ)",
    "SPAIN GRANTS BAIL TO PRO-PALESTINIAN ACTIVIST CHAMBERS (AJ)",
    "BURNHAM: UK TO EXPLORE EVEN CLOSER EU TIES AFTER DEAL (BBC)",
    "PETROBRAS CLOSES AT A THREE-MONTH LOW IN THE ROUT (RIO TIMES)",
    "AL JAZEERA AT 30: THREE CHANNELS, 33 PROGRAMMES UNVEILED (AJ)",
    "US APPROVED SALES OF NEARLY 900,000 AI CHIPS TO CHINA (AJ)",
    "KUSHNER: RUSSIA 'COMFORTABLE' WITH NATO-LIKE UKRAINE DEAL (AJ)",
    "DEPARDIEU INVESTIGATED OVER SEXUAL ALLEGATIONS (BBC)",
    "BANCO DO BRASIL: INTRUDERS ACCESSED CUSTOMER DATA (LATIN TIMES)",
]

MAP_LEGEND = [
    "1 NEW YORK - 2 ANTALYA - 3 RIYADH - 4 KYIV - 5 BERLIN - 6 COPENHAGEN - "
    "7 LOS ANGELES - 8 JOHANNESBURG - 9 SEOUL - 10 PARIS",
    "11 THE HAGUE - 12 WARSAW - 13 BAGHDAD - 14 NEW DELHI - 15 TALLINN - "
    "16 ADDIS ABABA - 17 WASHINGTON DC - 18 SF BAY AREA",
]

DATE_CHECK = [
    "THU: SHENZHEN SUMMIT'S PEACE DECLARATION - ICJ'S MYANMAR GENOCIDE "
    "RULING - ANTHROPIC'S IPO DEBUT",
    "FRI: KYIV BRIDGE BARRAGE - MISSILES DOWN IN POLAND - CYCLONE AKVAN "
    "LANDFALL, 370,000+ EVACUATED",
]

# ---------------------------------------------------------------- layout

def centered(cv, y, s, col, scale, bold=False):
    draw_text(cv, (W - text_w(s, scale)) / 2, y, s, col, scale, bold)

def build():
    cv = Canvas()
    cv.rect(0, 0, W, H, PAPER)
    cv.frame(8, 8, W - 16, H - 16, INK, 2)
    M = 22

    # kicker
    cv.rect(M, 18, W - 2 * M, 26, RED)
    centered(cv, 24.5, "AI ROUT ROCKS WALL ST - CLIMATE TALKS STALL - "
             "MISSILES OVER RIYADH", WHITE, 1.55, bold=True)
    # masthead + date
    centered(cv, 52, "THE WORLD IN ONE DAY", INK, 5.2, bold=True)
    cv.hline(M, 98, W - 2 * M, INK, 2)
    centered(cv, 104, "SATURDAY 21 NOVEMBER 2026", RED, 3.3, bold=True)
    cv.hline(M, 134, W - 2 * M, INK, 2)
    centered(cv, 139, "ONE IMAGE - 36 STORIES - EVERY FIGURE ATTRIBUTED "
             "TO ITS SOURCE", GREY, 1.4)

    # stat strip
    sy = 156
    cv.hline(M, sy - 4, W - 2 * M, LGREY, 1)
    for i, (val, cap) in enumerate(STATS):
        cx = M + i * 163
        draw_text(cv, cx, sy, val, RED if i % 2 == 0 else BLUE, 2.5, bold=True)
        draw_wrapped(cv, cx, sy + 21, cap, INK, 1.0, 152, 9, max_lines=3)
    cv.hline(M, sy + 52, W - 2 * M, INK, 1)

    # leads
    ly = 218
    for i, (tag, ill, head, body) in enumerate(LEADS):
        cx = M + i * 331
        cw = 317
        cv.frame(cx, ly, cw, 226, INK, 1)
        ill(cv, cx + 6, ly + 6, cw - 12, 100)
        draw_text(cv, cx + 9, ly + 112, tag, RED, 1.25, bold=True)
        draw_wrapped(cv, cx + 9, ly + 126, head, INK, 1.85, cw - 18, 15.5,
                     max_lines=2)
        draw_wrapped(cv, cx + 9, ly + 160, body, INK, 1.32, cw - 18, 11.3,
                     max_lines=6)

    # map
    draw_text(cv, M, 450, "WHERE IT HAPPENED - THE DAY PINNED TO THE MAP",
              INK, 1.3, bold=True)
    draw_map(cv)
    for i, ln in enumerate(MAP_LEGEND):
        centered(cv, 638 + i * 11, ln, GREY, 1.12)

    # features
    fy = 664
    draw_text(cv, M, fy - 2, "ALSO TODAY - TEN MORE STORIES", INK, 1.3,
              bold=True)
    for i, (head, body) in enumerate(FEATURES):
        cx = M + (i % 5) * 198
        cy = fy + 12 + (i // 5) * 74
        cw = 188
        cv.frame(cx, cy, cw, 68, LGREY, 1)
        ICONS[i](cv, cx + 5, cy + 5, BLUE if i % 2 == 0 else TEAL)
        draw_wrapped(cv, cx + 46, cy + 7, head, INK, 1.22, cw - 52, 10,
                     max_lines=3)
        draw_wrapped(cv, cx + 7, cy + 40, body, INK, 0.95, cw - 12, 8.5,
                     max_lines=3)

    # briefs
    by = 824
    draw_text(cv, M, by, "IN BRIEF - THE REST OF SATURDAY'S WORLD", INK, 1.3,
              bold=True)
    cv.hline(M, by + 12, W - 2 * M, INK, 1)
    cols = 4
    per = 6
    for c in range(cols):
        cx = M + c * 247
        for r in range(per):
            idx = c * per + r
            if idx >= len(BRIEFS):
                break
            draw_wrapped(cv, cx, by + 20 + r * 20, "%d. %s" % (idx + 1,
                         BRIEFS[idx]), INK, 1.0, 238, 9, max_lines=2)

    # date check
    dy = 966
    cv.rect(M, dy, W - 2 * M, 32, DARK)
    draw_text(cv, M + 8, dy + 3, "DATE CHECK - BIG STORIES LEFT OUT: NOT "
              "SATURDAY'S NEWS", GOLD, 1.05, bold=True)
    draw_text(cv, M + 8, dy + 13, DATE_CHECK[0], WHITE, 0.92)
    draw_text(cv, M + 8, dy + 22, DATE_CHECK[1], WHITE, 0.92)
    # footer
    centered(cv, 1003, "CLAIMS ARE ATTRIBUTED, NOT STATED AS FACT - "
             "SOURCES: REUTERS - AP - BBC - AL JAZEERA - WSJ - CNN - IMD - "
             "ISW - RIO TIMES - LATIN TIMES - KOREA JOONGANG DAILY",
             GREY, 0.95)
    return cv

def main():
    cv = build()
    data = png_bytes(W, H, cv.downsample())
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "entry.png"), "wb") as f:
        f.write(data)

if __name__ == "__main__":
    main()
