#!/usr/bin/env python3
"""THE WORLD IN ONE DAY - Saturday 21 November 2026.

A deterministic, offline, standard-library-only program that draws a
broadsheet front page summing up the world's news of 21 November 2026
and writes it to /output/entry.png (1024x1024 PNG, under 1 MiB).

Every story was reported on 21 November 2026 by the named source; the
figures are the sources' own. Type is a proportional serif + sans drawn
from vector stroke skeletons, rasterised with a signed-distance field
so print stays crisp at every size. Rendering is done at 2x and
box-downsampled. No network, no randomness, no clock.
"""

import math
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

    def blend_rect(self, x, y, w, h, col, alpha):
        """Alpha-blend a rect (alpha 0..255) over what is already drawn."""
        x, y, w, h = int(x * SS), int(y * SS), int(w * SS), int(h * SS)
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, CW), min(y + h, CH)
        ia = 255 - alpha
        for yy in range(y0, y1):
            i = (yy * CW + x0) * 3
            for xx in range(x0, x1):
                self.px[i]     = (col[0] * alpha + self.px[i] * ia) // 255
                self.px[i + 1] = (col[1] * alpha + self.px[i + 1] * ia) // 255
                self.px[i + 2] = (col[2] * alpha + self.px[i + 2] * ia) // 255
                i += 3

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

    def line(self, x0, y0, x1, y1, col, t=2):
        """Thick line via dense disc stamps along the segment."""
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist * 2))
        for i in range(steps + 1):
            f = i / steps
            self.disc(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, t / 2.0, col)

    def poly(self, pts, col):
        """Filled polygon, points in final-image coordinates."""
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

# ------------------------------------------------------------ font engine
# Glyph space: em 100, baseline y=0, cap height 70, x-height 50, desc -22.
# Each glyph: (advance, strokes, serifs, dots)
#   strokes: list of polylines, each a list of (x, y) in glyph units, y up
#   serifs:  list of (x, y) slab centres (serif face only)
#   dots:    list of (x, y, r) filled discs

def _arc(cx, cy, rx, ry, a0, a1, n=None):
    if n is None:
        n = max(6, int(abs(a1 - a0) / 7))
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts

def _V(x, y0, y1): return [(x, y0), (x, y1)]

def _SM(pts):
    """Flag a polyline for Catmull-Rom smoothing at tile-build time."""
    return ('~', pts)

def _smooth(pts, subdiv=4):
    if len(pts) < 3:
        return pts
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for j in range(subdiv):
            t = j / subdiv
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    out.append(pts[-1])
    return out
def _H(y, x0, x1): return [(x0, y), (x1, y)]
def _L(x0, y0, x1, y1): return [(x0, y0), (x1, y1)]

GLYPHS = {
"A": (58, [_L(4,0,29,70), _L(54,0,29,70), _H(24,18,40)], [(4,2),(54,2)], []),
"B": (56, [_V(10,0,70), _H(70,10,34), _arc(34,52,15,18,90,-90), _H(34,10,38),
           _arc(38,17,17,17,90,-90), _H(0,10,38)], [(10,68),(10,2)], []),
"C": (58, [_arc(32,35,24,35,58,302)], [], []),
"D": (60, [_V(10,0,70), _H(70,10,32), _arc(32,35,24,35,90,-90), _H(0,10,32)],
      [(10,68),(10,2)], []),
"E": (50, [_V(10,0,70), _H(70,10,44), _H(36,10,38), _H(0,10,46)],
      [(10,68),(10,2)], []),
"F": (46, [_V(10,0,70), _H(70,10,44), _H(36,10,36)], [(10,2)], []),
"G": (62, [_arc(33,35,26,35,52,308), _L(50,28,50,9), _H(28,33,50)], [], []),
"H": (60, [_V(8,0,70), _V(50,0,70), _H(35,8,50)],
      [(8,68),(8,2),(50,68),(50,2)], []),
"I": (26, [_V(13,0,70)], [(13,68,10.5),(13,2,10.5)], []),
"J": (42, [_V(38,18,70), _arc(21,18,17,18,0,-180)], [(38,68)], []),
"K": (56, [_V(10,0,70), _L(48,70,13,33), _L(17,37,50,0)], [(10,68),(10,2)], []),
"L": (48, [_V(10,0,70), _H(0,10,44)], [(10,68)], []),
"M": (72, [_V(6,0,70), _L(6,70,36,26), _L(66,70,36,26), _V(66,0,70)],
      [(6,2),(6,68),(66,2),(66,68)], []),
"N": (62, [_V(8,0,70), _L(8,70,54,0), _V(54,0,70)],
      [(8,2),(8,68),(54,2),(54,68)], []),
"O": (64, [_arc(32,35,27,35,0,360,28)], [], []),
"P": (54, [_V(10,0,70), _H(70,10,36), _arc(36,52,16,18,90,-90), _H(34,10,36)],
      [(10,2)], []),
"Q": (64, [_arc(32,35,27,35,0,360,28), _L(38,12,58,-6)], [], []),
"R": (56, [_V(10,0,70), _H(70,10,36), _arc(36,52,16,18,90,-90), _H(34,10,36),
           _L(30,32,52,0)], [(10,2)], []),
"S": (56, [_SM([(48,60),(38,69),(22,68),(13,58),(16,47),(27,40),(41,33),(48,24),(43,9),(28,1),(14,3),(10,12)])], [], []),
"T": (54, [_H(70,4,50), _V(27,0,70)], [(27,2)], []),
"U": (60, [_V(8,16,70), _arc(30,16,22,16,180,360), _V(52,16,70)],
      [(8,68),(52,68)], []),
"V": (56, [_L(4,70,28,0), _L(52,70,28,0)], [], []),
"W": (64, [[(2,70),(16,0),(31,56),(46,0),(60,70)]], [], []),
"X": (54, [_L(6,0,48,70), _L(6,70,48,0)], [], []),
"Y": (54, [_L(4,70,27,32), _L(50,70,27,32), _V(27,0,32)], [(27,2)], []),
"Z": (52, [_H(70,8,46), _L(46,70,8,0), _H(0,8,46)], [], []),
"a": (52, [_arc(24,25,20,25,0,360,24), _V(44,0,50)], [(44,2)], []),
"b": (52, [_V(10,0,72), _arc(27,25,19,25,0,360,24)], [(10,2)], []),
"c": (48, [_arc(24,25,20,25,55,305)], [], []),
"d": (52, [_arc(25,25,19,25,0,360,24), _V(44,0,72)], [(44,2)], []),
"e": (50, [_arc(24,25,20,25,38,322), _H(26,6,40)], [], []),
"f": (30, [_SM([(30,66),(24,72),(16,70),(14,58),(14,0)]), _H(32,4,26)],
      [], []),
"g": (52, [_arc(24,26,20,24,0,360,24), _V(44,-10,50), _arc(30,-10,14,14,0,-170)], [], []),
"h": (48, [_V(10,0,72), _arc(24,32,14,18,180,0), _V(38,0,32)], [(10,2)], []),
"i": (24, [_V(12,0,50)], [(12,2),(12,48)], [(12,64,3.6)]),
"j": (26, [_V(20,-8,50), _arc(8,-8,12,12,0,-140)], [], [(20,64,3.6)]),
"k": (46, [_V(10,0,72), _L(36,50,12,24), _L(16,28,38,0)], [(10,2)], []),
"l": (24, [_V(12,0,72)], [(12,2,8.5),(12,70,8.5)], []),
"m": (60, [_V(8,0,50), _arc(19,36,11,14,180,0), _V(30,0,36), _arc(41,36,11,14,180,0), _V(52,0,36)], [(8,2)], []),
"n": (48, [_V(10,0,50), _arc(24,32,14,18,180,0), _V(38,0,32)], [(10,2)], []),
"o": (50, [_arc(25,25,21,25,0,360,24)], [], []),
"p": (52, [_V(10,-22,50), _arc(27,25,19,25,0,360,24)], [], []),
"q": (52, [_arc(25,25,19,25,0,360,24), _V(44,-22,50)], [], []),
"r": (34, [_V(10,0,50), [(10,32),(14,44),(22,50),(30,45)]], [(10,2)], []),
"s": (44, [_SM([(40,43),(30,50),(14,47),(8,37),(14,28),(27,22),(36,14),(30,3),(15,0),(7,6)])], [], []),
"t": (32, [_V(16,4,66), _H(38,6,28), [(16,8),(18,2),(24,1)]], [], []),
"u": (50, [_V(10,16,50), _arc(25,16,15,16,180,360), _V(40,0,50)], [], []),
"v": (46, [_L(4,50,23,0), _L(42,50,23,0)], [], []),
"w": (52, [[(2,50),(14,0),(25,42),(36,0),(48,50)]], [], []),
"x": (44, [_L(6,0,38,50), _L(6,50,38,0)], [], []),
"y": (46, [_L(4,50,23,16), _L(42,50,23,16), _L(23,16,10,-20)], [], []),
"z": (44, [_H(50,8,38), _L(38,50,8,0), _H(0,8,38)], [], []),
"0": (56, [_arc(28,35,22,35,0,360,26)], [], []),
"1": (40, [_L(15,57,30,70), _V(30,0,70), _H(0,15,45)], [], []),
"2": (52, [_arc(26,53,16,17,150,-90), _L(26,36,10,2), _H(0,10,46)], [], []),
"3": (52, [_arc(25,52,15,18,90,-95), _arc(27,17,17,17,90,-90),
           _H(70,11,25), _H(0,11,27)], [], []),
"4": (54, [_V(38,0,70), _H(26,10,52), _L(10,26,38,70)], [], []),
"5": (50, [_H(70,12,44), _V(12,38,70), _L(12,38,27,40),
           _arc(28,20,16,20,90,-90), _H(0,12,28)], [], []),
"6": (52, [_SM([(42,64),(30,58),(18,40),(16,31)]),
           _arc(27,19,16,19,0,360,24)], [], []),
"7": (50, [_H(70,8,46), _L(46,70,24,0)], [], []),
"8": (52, [_arc(26,52,13,17,0,360,20), _arc(26,19,16,19,0,360,22)], [], []),
"9": (52, [_arc(25,51,16,19,0,360,24),
           _SM([(41,50),(38,28),(26,8),(13,3)])], [], []),
" ": (26, [], [], []),
".": (24, [], [], [(12,2,3.4)]),
",": (24, [_L(14,2,9,-8)], [], [(12,3,3.4)]),
"'": (18, [_L(8,56,12,72)], [], []),
":": (24, [], [], [(12,2,3.4),(12,32,3.4)]),
";": (24, [_L(14,2,9,-8)], [], [(12,33,3.4),(12,3,3.4)]),
"!": (24, [_V(12,16,70)], [], [(12,2,3.6)]),
"?": (44, [_arc(21,53,12,15,180,-90), _V(21,14,38)], [], [(21,2,3.6)]),
"-": (36, [_H(30,6,30)], [], []),
"\u2014": (60, [_H(30,4,56)], [], []),
"\u00b7": (20, [], [], [(10,26,3.2)]),
"(": (30, [_arc(22,25,13,47,115,245)], [], []),
")": (30, [_arc(8,25,13,47,-65,65)], [], []),
"$": (48, [_SM([(43,60),(34,68),(21,67),(13,58),(15,48),(24,41),(37,34),
            (44,25),(40,10),(27,2),(14,4),(11,11)]), _V(24,-6,76)], [], []),
"%": (64, [_arc(14,56,8,10,0,360,12), _arc(50,14,8,10,0,360,12),
           _L(52,72,12,-2)], [], []),
"+": (44, [_H(35,8,36), _V(22,12,58)], [], []),
"&": (52, [[(40,8),(22,40),(14,56),(19,68),(29,64),(24,44),(10,26),(8,12),
            (15,2),(28,4),(36,12)], _L(28,20,46,0)], [], []),
'"': (28, [_L(8,56,11,72), _L(20,56,23,72)], [], []),
"*": (36, [_V(18,42,64), _L(9,47,27,59), _L(9,59,27,47)], [], []),
"#": (48, [_V(16,4,64), _V(32,4,64), _H(44,8,40), _H(22,8,40)], [], []),
"=": (44, [_H(42,8,36), _H(22,8,36)], [], []),
"/": (36, [_L(30,72,6,-2)], [], []),
"<": (44, [[(34,56),(12,33),(34,10)]], [], []),
">": (44, [[(10,56),(32,33),(10,10)]], [], []),
"~": (44, [[(6,32),(14,40),(22,32),(30,24),(38,32)]], [], []),
}

Y_TOP, Y_BOT = 80.0, -28.0     # glyph-space vertical extent of a tile
X_PAD = 8.0                    # horizontal padding in glyph units

def _seg_hw(p0, p1, face, bold):
    """Half width of one segment: serif width follows segment direction
    (verticals thick, horizontals thin); sans is uniform."""
    if face == 'sans':
        return (12.8 if bold else 8.6) / 2.0
    thick, thin = (12.6, 6.4) if bold else (8.4, 4.3)
    dx = p1[0] - p0[0]; dy = p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1.0
    f = abs(dy) / ln
    return (thin + (thick - thin) * f) / 2.0

_tile_cache = {}

def glyph_tile(ch, face, bold, size):
    """Alpha tile via signed distance field: for every pixel, f = min over
    all primitives of (distance - half width), in device px. Coverage =
    clamp(0.5 - f/1.5). Round joins/caps fall out of the distance field
    automatically, so curves render smooth at every size.
    Returns (w, h, sparse); tile origin: glyph (-X_PAD, Y_TOP) -> (0,0)."""
    key = (ch, face, bold, round(size * 4))
    if key in _tile_cache:
        return _tile_cache[key]
    g = GLYPHS.get(ch) or GLYPHS[" "]
    adv, strokes, serifs, dots = g
    k = size / 100.0 * SS          # glyph unit -> device px
    inv_k = 1.0 / k
    tw = int(math.ceil((adv + 2 * X_PAD) * k))
    th = int(math.ceil((Y_TOP - Y_BOT) * k))
    segs = []
    for st in strokes:
        if isinstance(st, tuple):        # ('~', pts) -> smoothed polyline
            st = _smooth(st[1])
        for i in range(len(st) - 1):
            segs.append((st[i][0], st[i][1], st[i + 1][0], st[i + 1][1],
                         _seg_hw(st[i], st[i + 1], face, bold)))
    rects = []
    if face == 'serif':
        shh = (3.4 if bold else 2.8) / 2.0
        for sf in serifs:
            sw = sf[2] if len(sf) > 2 else (10.0 if bold else 9.0)
            rects.append((sf[0], sf[1], sw, shh))
    INF = 1e9
    f = [INF] * (tw * th)
    pad_extra = 1.8 * inv_k

    def upd_seg(x0, y0, x1, y1, hw):
        pad = hw + pad_extra
        px0 = max(int(math.floor((min(x0, x1) - pad + X_PAD) * k)), 0)
        px1 = min(int(math.ceil((max(x0, x1) + pad + X_PAD) * k)), tw - 1)
        py0 = max(int(math.floor((Y_TOP - max(y0, y1) - pad) * k)), 0)
        py1 = min(int(math.ceil((Y_TOP - min(y0, y1) + pad) * k)), th - 1)
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-9
        hwpx = hw * k
        for py in range(py0, py1 + 1):
            gy = Y_TOP - (py + 0.5) * inv_k
            row = py * tw
            for px in range(px0, px1 + 1):
                gx = (px + 0.5) * inv_k - X_PAD
                t = ((gx - x0) * dx + (gy - y0) * dy) / L2
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                ddx = gx - (x0 + t * dx); ddy = gy - (y0 + t * dy)
                d = math.sqrt(ddx * ddx + ddy * ddy) * k - hwpx
                idx = row + px
                if d < f[idx]:
                    f[idx] = d

    def upd_disc(cx, cy, r):
        pad = r + pad_extra
        px0 = max(int(math.floor((cx - pad + X_PAD) * k)), 0)
        px1 = min(int(math.ceil((cx + pad + X_PAD) * k)), tw - 1)
        py0 = max(int(math.floor((Y_TOP - cy - pad) * k)), 0)
        py1 = min(int(math.ceil((Y_TOP - cy + pad) * k)), th - 1)
        rpx = r * k
        for py in range(py0, py1 + 1):
            gy = Y_TOP - (py + 0.5) * inv_k
            row = py * tw
            for px in range(px0, px1 + 1):
                gx = (px + 0.5) * inv_k - X_PAD
                d = math.hypot(gx - cx, gy - cy) * k - rpx
                idx = row + px
                if d < f[idx]:
                    f[idx] = d

    def upd_rect(cx, cy, hw, hh):
        pad = max(hw, hh) + pad_extra
        px0 = max(int(math.floor((cx - pad + X_PAD) * k)), 0)
        px1 = min(int(math.ceil((cx + pad + X_PAD) * k)), tw - 1)
        py0 = max(int(math.floor((Y_TOP - cy - pad) * k)), 0)
        py1 = min(int(math.ceil((Y_TOP - cy + pad) * k)), th - 1)
        for py in range(py0, py1 + 1):
            gy = Y_TOP - (py + 0.5) * inv_k
            row = py * tw
            for px in range(px0, px1 + 1):
                gx = (px + 0.5) * inv_k - X_PAD
                qx = abs(gx - cx) - hw; qy = abs(gy - cy) - hh
                ax = qx if qx > 0.0 else 0.0; ay = qy if qy > 0.0 else 0.0
                d = (math.hypot(ax, ay) + min(max(qx, qy), 0.0)) * k
                idx = row + px
                if d < f[idx]:
                    f[idx] = d

    for s in segs:
        upd_seg(*s)
    for (dx, dy, r) in dots:
        upd_disc(dx, dy, r)
    for r in rects:
        upd_rect(*r)
    sparse = []
    for idx, d in enumerate(f):
        if d < 0.75:
            a = 0.5 - d / 1.5
            if a > 0.04:
                sparse.append((idx, int(min(a, 1.0) * 255)))
    out = (tw, th, sparse)
    _tile_cache[key] = out
    return out

def text_w(s, face, bold, size, tracking=0.0):
    k = size / 100.0
    w = 0.0
    for ch in s:
        g = GLYPHS.get(ch) or GLYPHS[" "]
        w += g[0] * k
    if len(s) > 1:
        w += tracking * (len(s) - 1)
    return w

def draw_text(cv, x, y_base, s, col, face='serif', bold=False, size=16.0,
              tracking=0.0):
    """Draw s with baseline at y_base (final px). Returns x past the text."""
    k = size / 100.0
    cx = x
    inv = [255 - c for c in col]
    for ch in s:
        g = GLYPHS.get(ch) or GLYPHS[" "]
        tw, th, sparse = glyph_tile(ch, face, bold, size)
        ox = int(round((cx - X_PAD * k) * SS))
        oy = int(round((y_base - Y_TOP * k) * SS))
        for idx, a in sparse:
            tx = idx % tw; ty = idx // tw
            px = ox + tx; py = oy + ty
            if 0 <= px < CW and 0 <= py < CH:
                i = (py * CW + px) * 3
                ia = 255 - a
                cv.px[i]     = (col[0] * a + cv.px[i] * ia) // 255
                cv.px[i + 1] = (col[1] * a + cv.px[i + 1] * ia) // 255
                cv.px[i + 2] = (col[2] * a + cv.px[i + 2] * ia) // 255
        cx += g[0] * k + tracking
    return cx - (tracking if s else 0)

def wrap(s, face, bold, size, max_w, tracking=0.0):
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        trial = wd if not cur else cur + " " + wd
        if text_w(trial, face, bold, size, tracking) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines

def draw_wrapped(cv, x, y_base, s, col, face, bold, size, max_w, line_h,
                 max_lines=None, tracking=0.0):
    lines = wrap(s, face, bold, size, max_w, tracking)
    if max_lines is not None:
        lines = lines[:max_lines]
    for i, ln in enumerate(lines):
        draw_text(cv, x, y_base + i * line_h, ln, col, face, bold, size,
                  tracking)
    return y_base + len(lines) * line_h

# ---------------------------------------------------------------- palette

PAPER = (246, 241, 230)
INK = (17, 17, 19)
INK2 = (44, 44, 48)          # secondary text, still near-black
RED = (164, 24, 30)
NAVY = (22, 40, 84)
NAVY_D = (15, 21, 40)
GOLD = (198, 146, 44)
TEAL = (13, 98, 92)
GREY = (84, 82, 78)
LGREY = (178, 170, 152)
WHITE = (252, 250, 244)
TAN = (196, 172, 124)
SEA = (24, 44, 78)
SKY_T = (208, 228, 240)
SKY_B = (164, 198, 224)

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

MAP_X, MAP_Y, MAP_W, MAP_H = 28, 758, 470, 188
LON0, LON1 = -180, 180
LAT0, LAT1 = 82, -58          # top, bottom

def project(lon, lat):
    x = MAP_X + (lon - LON0) / (LON1 - LON0) * MAP_W
    y = MAP_Y + (LAT0 - lat) / (LAT0 - LAT1) * MAP_H
    return x, y

# (number, lon, lat, disc nudge dx, dy) — the disc sits on the point;
# nudges only where pins would collide (Europe, US coasts)
PINS = [
    (1, -74.0, 40.7, -6, -8),       # New York
    (2, 30.7, 36.9, -8, 4),         # Antalya
    (3, 46.7, 24.6, 8, 6),          # Riyadh
    (4, 30.5, 50.4, 12, -4),        # Kyiv
    (5, 13.4, 52.5, -2, 10),        # Berlin
    (6, 12.6, 55.7, 2, -12),        # Copenhagen
    (7, -118.2, 34.1, 4, 8),        # Los Angeles
    (8, 28.0, -26.2, 0, 0),         # Johannesburg
    (9, 127.0, 37.6, 0, 0),         # Seoul
    (10, 2.35, 48.9, -12, 6),       # Paris
    (11, 4.5, 52.1, -8, -8),        # The Hague
    (12, 21.0, 52.2, 10, 6),        # Warsaw
    (13, 44.4, 33.3, -6, -4),       # Baghdad
    (14, 77.2, 28.6, 0, 0),         # New Delhi
    (15, 24.7, 59.4, 8, -8),        # Tallinn
    (16, 106.8, -6.2, 0, 0),        # Jakarta
    (17, -77.0, 38.9, 8, 10),       # Washington DC
    (18, -122.0, 37.4, -10, -8),    # San Francisco Bay Area
]

def draw_map(cv):
    cv.rect(MAP_X, MAP_Y, MAP_W, MAP_H, SEA)
    for poly in CONTINENTS:
        cv.poly([project(lon, lat) for lon, lat in poly], TAN)
    cv.frame(MAP_X, MAP_Y, MAP_W, MAP_H, INK, 1)
    for num, lon, lat, dx, dy in PINS:
        x, y = project(lon, lat)
        # true-position dot: white ring, red core, exactly on the lon/lat
        cv.disc(x, y, 2.8, WHITE)
        cv.disc(x, y, 1.8, RED)
        # numbered disc centred on the (possibly nudged) point
        cx, cy = x + dx, y + dy
        cv.disc(cx, cy, 6.8, RED)
        label = str(num)
        tw = text_w(label, 'sans', True, 9.5)
        draw_text(cv, cx - tw / 2, cy + 3.4, label, WHITE,
                  'sans', True, 9.5)

# ---------------------------------------------------------------- lead art
# Flat-colour scenes, drawn dense: texture first, then the shapes.

def ill_markets(cv, x, y, w, h):
    cv.rect(x, y, w, h, NAVY_D)
    grid = (44, 54, 86)
    gy = y + 12
    while gy < y + h - 44:
        cv.hline(x + 6, gy, w - 12, grid, 1)
        gy += 13
    gx = x + 14
    while gx < x + w - 6:
        cv.vline(gx, y + 5, h - 50, grid, 1)
        gx += 34
    # candlesticks on a falling path
    tops = [0.10, 0.16, 0.13, 0.22, 0.28, 0.25, 0.36, 0.42, 0.40, 0.52,
            0.58, 0.66]
    for i, tf in enumerate(tops):
        cx = x + 14 + i * (w - 34) / 11
        top = y + 8 + tf * (h - 66)
        bh = 9 + (i * 7 % 9)
        col = (232, 84, 66) if i % 3 else GOLD
        cv.line(cx, top - 5, cx, top + bh + 5, col, 1.4)
        cv.rect(cx - 3.4, top, 6.8, bh, col)
    pts = [(x + 14 + i * (w - 34) / 11, y + 8 + tf * (h - 66))
           for i, tf in enumerate(tops)]
    for a, b in zip(pts, pts[1:]):
        cv.line(a[0], a[1], b[0], b[1], (244, 102, 84), 2.6)
    ex, ey = pts[-1]
    cv.poly([(ex + 2, ey + 2), (ex - 12, ey - 1), (ex - 3, ey - 11)],
            (244, 102, 84))
    # volume bars along the bottom of the scene
    for i in range(16):
        bh = 4 + (i * 11 % 13)
        cv.rect(x + 10 + i * (w - 20) / 16, y + h - 42 - bh, 7, bh,
                (96, 60, 60) if i % 2 else (120, 96, 52))

def ill_climate(cv, x, y, w, h):
    bands = 6
    for i in range(bands):
        f = i / (bands - 1)
        col = tuple(int(SKY_T[c] + (SKY_B[c] - SKY_T[c]) * f)
                    for c in range(3))
        cv.rect(x, y + h * i / bands, w, h / bands + 1, col)
    # clouds: overlapping white discs
    for cx, cy, s in [(0.14, 0.20, 1.0), (0.30, 0.13, 0.7), (0.60, 0.16, 0.8)]:
        for dx, dy, r in [(-14, 0, 8), (0, -4, 11), (14, 0, 8), (4, 3, 9)]:
            cv.disc(x + w * cx + dx * s, y + h * cy + dy * s, r * s,
                    (250, 250, 246))
    # sun with rays, top right
    sx, sy = x + w - 30, y + 20
    cv.disc(sx, sy, 10, GOLD)
    for dx, dy in [(-16, 0), (16, 0), (0, -16), (-12, -12), (12, -12),
                   (-12, 12), (12, 12)]:
        cv.line(sx + dx * 0.75, sy + dy * 0.75, sx + dx, sy + dy, GOLD, 2)
    # sea strip (a shoreline the hall stands on)
    cv.rect(x, y + 66, w, 8, TEAL)
    for i in range(9):
        wx = x + 12 + i * (w - 24) / 8
        cv.line(wx, y + 70, wx + 7, y + 70, (168, 224, 214), 1.4)
    # conference hall: dome + columns on the shore
    base = y + 66
    hw_ = w - 120
    hx = x + 22
    cv.rect(hx, base - 26, hw_, 26, WHITE)
    cv.frame(hx, base - 26, hw_, 26, INK, 1)
    cxm = hx + hw_ / 2
    for i in range(41):
        f = i / 40
        dx = (f - 0.5) * hw_
        dy = -math.sin(f * math.pi) * 24
        cv.disc(cxm + dx, base - 26 + dy, 2.6, NAVY)
        cv.disc(cxm + dx * 0.8, base - 26 + dy * 0.8, 1.4, NAVY)
    for i in range(6):
        cv.rect(hx + 8 + i * (hw_ - 16) / 5, base - 22, 4, 18, NAVY)
    # flags on the roofline
    flag_cols = [RED, GOLD, TEAL, NAVY, (120, 60, 140), (30, 130, 60)]
    for i, fc in enumerate(flag_cols):
        fx = hx + 12 + i * (hw_ - 24) / 5
        cv.vline(fx, base - 40, 12, INK, 1)
        cv.rect(fx + 1, base - 40, 7, 4.5, fc)
    # thermometer, right
    tx = x + w - 34
    cv.rect(tx, y + 12, 9, 44, WHITE)
    cv.frame(tx, y + 12, 9, 44, INK, 1)
    cv.rect(tx + 2, y + 24, 5, 30, RED)
    cv.disc(tx + 4.5, y + 58, 8.5, RED)

def ill_riyadh(cv, x, y, w, h):
    cv.rect(x, y, w, h, (13, 17, 36))
    for i in range(70):                          # stars, fixed pattern
        sx = x + (i * 67 % 199) / 199 * w
        sy = y + (i * 41 % 89) / 89 * h * 0.52
        cv.rect(sx, sy, 1.5, 1.5, (216, 222, 238))
    # crescent moon
    cv.disc(x + w - 28, y + 18, 8, (228, 230, 238))
    cv.disc(x + w - 24, y + 15, 7, (13, 17, 36))
    base = y + h
    towers = [(0.01, 0.09, 0.52), (0.11, 0.06, 0.75), (0.18, 0.08, 0.46),
              (0.27, 0.05, 0.87), (0.33, 0.09, 0.58), (0.43, 0.06, 0.70),
              (0.50, 0.08, 0.49), (0.59, 0.05, 0.81), (0.65, 0.09, 0.61),
              (0.75, 0.06, 0.73), (0.82, 0.08, 0.52), (0.91, 0.08, 0.67)]
    for bx, bw, bh in towers:                    # far skyline, lighter
        cv.rect(x + w * (bx + 0.03), base - h * bh * 0.62, w * bw,
                h * bh * 0.62, (36, 46, 80))
    for bx, bw, bh in towers:
        tx, ty = x + w * bx, base - h * bh
        tw_, th_ = w * bw, h * bh
        cv.rect(tx, ty, tw_, th_, (32, 40, 72))
        # lit windows in a fixed pattern
        rows = int(th_ / 9)
        cols = max(1, int(tw_ / 8))
        for r in range(rows):
            for c in range(cols):
                if (r * 7 + c * 13 + int(bx * 100)) % 5 < 2:
                    cv.rect(tx + 2 + c * 8, ty + 3 + r * 9, 2.6, 3.4,
                            (240, 205, 120))
    cv.rect(x, base - 40, w, 40, (10, 13, 26))
    # interceptor arcs with starbursts
    for sx, ex, peak in [(0.06, 0.46, 0.78), (0.28, 0.68, 0.92),
                         (0.52, 0.94, 0.72)]:
        for i in range(31):
            f = i / 30
            ax = x + w * (sx + (ex - sx) * f)
            ay = base - 40 - math.sin(f * math.pi) * h * peak * 0.62
            cv.disc(ax, ay, 1.7, GOLD)
        bx, by = x + w * ex, base - 40 - h * peak * 0.62
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            cv.line(bx, by, bx + 7 * math.cos(a), by + 7 * math.sin(a),
                    (246, 150, 80), 1.6)
        cv.disc(bx, by, 2.6, (250, 190, 110))

# ---------------------------------------------------------------- content
# The 36 stories of Saturday 21 November 2026, word for word as built
# and audited in v1/v2 — only letter case is normalised for print
# (sentence case; acronyms and proper nouns keep their capitals).

STATS = [
    ("-10%", "Nasdaq's week — worst since March 2020 (WSJ)"),
    ("$4TN+", "Wiped off the Nasdaq's value this week (WSJ)"),
    ("-8.5%", "Anthropic Friday, $88.91 vs $83 IPO price (CNN)"),
    ("~200", "Countries deadlocked at COP31, Antalya (AP)"),
    ("3", "Houthi missiles intercepted over Saudi (AJ)"),
    ("25", "European countries in Gen Z protests (AJ)"),
]

LEADS = [
    ("MARKETS — LEAD STORY", ill_markets,
     "AI rout: Nasdaq's worst week since 2020",
     "The Nasdaq fell 5.3% Friday, 10% on the week — over $4 trillion "
     "gone (WSJ). Anthropic slid 8.5% to $88.91, barely above its $83 "
     "IPO price (CNN); Nvidia dropped 14% Friday (WSJ). Asia's markets "
     "dived (AJ)."),
    ("CLIMATE — LEAD STORY", ill_climate,
     "COP31 runs into overtime with no deal",
     "Nearly 200 countries still deadlocked in Antalya on Saturday. "
     "The latest draft drops all mention of fossil fuels and the "
     "$120bn-a-year adaptation target; a third draft was promised for "
     "Saturday (AP)."),
    ("MIDDLE EAST — LEAD STORY", ill_riyadh,
     "Third night of missiles over Riyadh",
     "The Saudi-led coalition said it intercepted three Houthi "
     "missiles. Iran's IRGC claimed it downed a US MQ-9 drone over "
     "the Strait of Hormuz (Al Jazeera)."),
]

FEATURES = [
    ("KYIV",
     "Zelensky: 'a killer'",
     "Trump called Putin his 'friend'; Zelensky told CNN: 'for us, "
     "he is a killer' (BBC)."),
    ("BERLIN",
     "Gen Z protests, 25 countries",
     "Thousands rallied across Europe on Friday over costs, war "
     "spending and climate (AJ)."),
    ("LOS ANGELES",
     "Palisades arsonist guilty",
     "A 30-year-old convicted over the fire that killed 12, burned "
     "6,800+ structures (BBC)."),
    ("COPENHAGEN",
     "Denmark expels diplomat",
     "A Russian diplomat expelled over an alleged plot to kill a "
     "US-Ukrainian rapper (AJ)."),
    ("NEW YORK",
     "Rikers to close by 2032",
     "Mayor Mamdani unveils a plan to shut New York's Rikers Island "
     "jail complex (BBC)."),
    ("JOHANNESBURG",
     "ANC fights for the cities",
     "The ANC fights to hold South Africa's key cities after a local "
     "election setback (BBC)."),
    ("WASHINGTON DC",
     "$811M bail-bond fraud",
     "US firms fined $811M for conning detained migrants — and the "
     "scams went on (BBC)."),
    ("SF BAY AREA",
     "Trump: bring back Huang",
     "Trump urges Nvidia to reinstate CEO Jensen Huang with a 'big "
     "apology' (AJ)."),
    ("JAKARTA",
     "Indonesia joins ICAO Council",
     "Elected to the UN aviation body's Council for 2026-2028 at the "
     "Montreal assembly (Antara)."),
    ("PARIS",
     "Zecler officers sentenced",
     "3 French officers sentenced over the racist assault on Michel "
     "Zecler (BBC)."),
]

BRIEFS = [
    "Myanmar and China object to the ICJ Rohingya genocide ruling (AJ)",
    "NATO chief Rutte due in Warsaw after missiles fell in Poland (AP)",
    "Iraqi forces deploy to Jurf al-Sakhar after militia deal (AJ)",
    "Trump threatens tax on US firms building AI data centres abroad (AJ)",
    "111 Suneung candidates found with banned smart devices (BBC)",
    "Nearly 600 women killed in South Africa in three months (BBC)",
    "Indian man gets 19+ years in US over Sikh separatist plot (BBC)",
    "Nigeria moves to end jail terms for attempted suicide (BBC)",
    "Judge approves $7.25bn Roundup cancer settlement (BBC)",
    "Texas execution took more than an hour, witnesses say (BBC)",
    "US declassifies more UFO footage from the Middle East (BBC)",
    "Nepal PM Shah arrives in India Sunday for first visit (BBC)",
    "Two landslides in Klungkung, Bali; damage near Rp1bn (Detik)",
    "Pochettino takes over at Man Utd; first game Sunday (AJ)",
    "Russia cries 'Iron Curtain' as Estonia shuts its borders (AJ)",
    "Spain grants bail to pro-Palestinian activist Chambers (AJ)",
    "Burnham: UK to explore even closer EU ties after deal (BBC)",
    "Petrobras closes at a three-month low in the rout (Rio Times)",
    "Indonesia-EU trade pact signing set for Brussels Saturday (Antara)",
    "US approved sales of nearly 900,000 AI chips to China (AJ)",
    "Kushner: Russia 'comfortable' with NATO-like Ukraine deal (AJ)",
    "Depardieu withdraws appeal, accepts 18-month suspended sentence (BBC)",
    "Bali sets 2027 minimum wage at Rp4.56M, up 42.15% (Bali Kini)",
]

MAP_LEGEND = [
    "1 New York — 2 Antalya — 3 Riyadh — 4 Kyiv — 5 Berlin",
    "6 Copenhagen — 7 Los Angeles — 8 Johannesburg — 9 Seoul",
    "10 Paris — 11 The Hague — 12 Warsaw — 13 Baghdad",
    "14 New Delhi — 15 Tallinn — 16 Jakarta — 17 Washington DC — "
    "18 SF Bay Area",
]

DATE_CHECK = [
    "Thu: Shenzhen summit's peace declaration — ICJ's Myanmar genocide "
    "ruling — Anthropic's IPO debut",
    "Fri: Kyiv bridge barrage — missiles down in Poland — Cyclone Akvan "
    "landfall, 370,000+ evacuated",
]

BAND_COLS = [NAVY, TEAL, (150, 96, 26), (104, 52, 120), (30, 110, 60)]

# ---------------------------------------------------------------- layout

M = 28
RIGHT = W - M

def centered(cv, y_base, s, col, face, bold, size, tracking=0.0):
    w = text_w(s, face, bold, size, tracking)
    draw_text(cv, (W - w) / 2, y_base, s, col, face, bold, size, tracking)

def right_aligned(cv, x_right, y_base, s, col, face, bold, size,
                  tracking=0.0):
    w = text_w(s, face, bold, size, tracking)
    draw_text(cv, x_right - w, y_base, s, col, face, bold, size, tracking)

def section_header(cv, x, y_base, s, size=12.5):
    cv.rect(x, y_base - 11, 4, 14, RED)
    draw_text(cv, x + 10, y_base, s, INK, 'sans', True, size, tracking=0.8)

def build():
    cv = Canvas()
    cv.rect(0, 0, W, H, PAPER)

    # ---- eyebrow: nameplate left, strapline right, then a rule
    draw_text(cv, M, 38, "THE WORLD IN ONE DAY", RED, 'sans', True, 13.5,
              tracking=1.6)
    right_aligned(cv, RIGHT, 38,
                  "ONE IMAGE · 36 STORIES · EVERY FIGURE ATTRIBUTED TO "
                  "ITS SOURCE", INK2, 'sans', False, 9.5, tracking=0.7)
    cv.hline(M, 47, W - 2 * M, INK, 2)

    # ---- the date, the biggest thing on the page
    date_s = "Saturday 21 November 2026"
    dsize = 96.0
    while text_w(date_s, 'serif', True, dsize) > 950 and dsize > 40:
        dsize -= 2.0
    centered(cv, 118, date_s, INK, 'serif', True, dsize)

    # ---- dek: the day in one line (the old kicker, as a serif dek)
    centered(cv, 148, "AI rout rocks Wall St — climate talks stall — "
             "missiles over Riyadh", RED, 'serif', False, 19.5)
    cv.hline(M, 160, W - 2 * M, INK, 3)
    cv.hline(M, 165, W - 2 * M, INK, 1)

    # ---- stat strip
    sw = (W - 2 * M) / 6
    for i, (val, cap) in enumerate(STATS):
        cx = M + i * sw
        if i:
            cv.vline(cx - 9, 178, 62, LGREY, 1)
        draw_text(cv, cx, 200, val, RED if i % 2 == 0 else NAVY,
                  'serif', True, 34)
        draw_wrapped(cv, cx, 218, cap, INK2, 'serif', False, 11.5,
                     sw - 16, 13.5, max_lines=3)
    cv.hline(M, 250, W - 2 * M, LGREY, 1)

    # ---- leads
    ly = 262
    lw = (W - 2 * M - 2 * 20) / 3
    for i, (tag, ill, head, body) in enumerate(LEADS):
        cx = M + i * (lw + 20)
        ill(cv, cx, ly, lw, 104)
        # red banner inside the art carries the headline
        lines = wrap(head, 'serif', True, 15.5, lw - 18)
        bh = 24 + 17 * (len(lines) - 1) + 8
        cv.rect(cx, ly + 104 - bh, lw, bh, RED)
        for j, ln in enumerate(lines[:2]):
            draw_text(cv, cx + 9, ly + 104 - bh + 17 + j * 17, ln, WHITE,
                      'serif', True, 15.5)
        # numbered red kicker, then the body
        draw_text(cv, cx, ly + 122, str(i + 1), RED, 'serif', True, 13)
        draw_text(cv, cx + 14, ly + 122, tag, RED, 'sans', True, 10.5,
                  tracking=0.7)
        draw_wrapped(cv, cx, ly + 144, body, INK, 'serif', False, 13,
                     lw - 4, 16.5, max_lines=5)

    # ---- features
    section_header(cv, M, 492, "ALSO TODAY — TEN MORE STORIES")
    fw = (W - 2 * M - 4 * 12) / 5
    for i, (city, head, body) in enumerate(FEATURES):
        cx = M + (i % 5) * (fw + 12)
        cy = 502 + (i // 5) * 97
        cv.frame(cx, cy, fw, 93, LGREY, 1)
        cv.rect(cx, cy, fw, 20, BAND_COLS[i % 5])
        draw_text(cv, cx + 7, cy + 14.5, city, WHITE, 'sans', True, 10,
                  tracking=0.8)
        draw_wrapped(cv, cx + 7, cy + 38, head, INK, 'serif', True, 14,
                     fw - 14, 15.5, max_lines=2)
        draw_wrapped(cv, cx + 7, cy + 68, body, INK2, 'serif', False, 10.8,
                     fw - 14, 12.2, max_lines=3)

    # ---- date check: a quiet bordered box
    dy = 700
    cv.frame(M, dy, W - 2 * M, 38, RED, 1)
    draw_text(cv, M + 10, dy + 15, "DATE CHECK — BIG STORIES LEFT OUT:",
              RED, 'sans', True, 10.5, tracking=0.6)
    draw_text(cv, M + 10, dy + 30, "NOT SATURDAY'S NEWS", RED, 'sans',
              True, 10.5, tracking=0.6)
    draw_wrapped(cv, M + 316, dy + 15, DATE_CHECK[0], INK2, 'serif',
                 False, 11, 320, 14, max_lines=2)
    draw_wrapped(cv, M + 652, dy + 15, DATE_CHECK[1], INK2, 'serif',
                 False, 11, 316, 14, max_lines=2)

    # ---- bottom zone: map + legend left, briefs right
    section_header(cv, M, 750, "WHERE IT HAPPENED — THE DAY PINNED TO "
                   "THE MAP", size=10.5)
    draw_map(cv)
    ly2 = 960
    for ln in MAP_LEGEND:
        ly2 = draw_wrapped(cv, M, ly2, ln, INK2, 'serif', False, 10,
                           MAP_W, 11.5) + 0.5

    bx = 526
    section_header(cv, bx, 750, "IN BRIEF — THE REST OF SATURDAY'S WORLD")
    col_w = (RIGHT - bx - 2 * 10) / 3
    # flow the briefs down three height-balanced columns, in order
    col_x = [bx + i * (col_w + 10) for i in range(3)]
    wrapped = [wrap(b, 'serif', False, 10.2, col_w - 15) for b in BRIEFS]
    needs = [len(ls) * 11.5 + 0.5 for ls in wrapped]
    target = sum(needs) / 3
    col_y = [756, 756, 756]
    cum = 0.0
    for n, lines in enumerate(wrapped):
        col = min(2, int(cum // target)) if target else 0
        x0, y0 = col_x[col], col_y[col]
        draw_text(cv, x0, y0 + 10.2, str(n + 1), RED, 'sans', True, 10.2)
        for j, ln in enumerate(lines):
            draw_text(cv, x0 + 15, y0 + 10.2 + j * 11.5, ln, INK,
                      'serif', False, 10.2)
        col_y[col] = y0 + needs[n]
        cum += needs[n]

    # ---- footer
    cv.hline(M, 1004, W - 2 * M, LGREY, 1)
    centered(cv, 1016, "Claims are attributed, not stated as fact — "
             "Sources: Reuters · AP · BBC · Al Jazeera · WSJ · CNN · "
             "IMD · ISW · Rio Times · Antara · Detik · Bali Kini · "
             "Korea JoongAng Daily",
             GREY, 'serif', False, 9.5)
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
