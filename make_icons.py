"""Genera los iconos PNG de la app sin dependencias: tele retro con antenas y "play" sobre degradado."""
import math, struct, zlib
from pathlib import Path


def png(path, w, h, px):
    raw = b"".join(b"\x00" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def rrect(x, y, cx, cy, hw, hh, r):  # distancia con signo a un rectángulo redondeado
    dx, dy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    return math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - r


def seg(x, y, ax, ay, bx, by):  # distancia a un segmento
    vx, vy, wx, wy = bx - ax, by - ay, x - ax, y - ay
    t = max(0, min(1, (wx * vx + wy * vy) / (vx * vx + vy * vy)))
    return math.hypot(wx - t * vx, wy - t * vy)


def tri(x, y, pts):  # dentro de un triángulo
    s = []
    for i in range(3):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % 3]
        s.append((bx - ax) * (y - ay) - (by - ay) * (x - ax) > 0)
    return all(s) or not any(s)


C_BG = [(30, 27, 75), (124, 58, 237), (219, 39, 119)]
WHITE, SCREEN, LIME, RED = (248, 250, 252), (14, 16, 34), (163, 230, 53), (255, 59, 107)


def color(x, y):
    t = (x + y) / 2  # degradado diagonal en dos tramos
    c = mix(C_BG[0], C_BG[1], t / .55) if t < .55 else mix(C_BG[1], C_BG[2], (t - .55) / .45)
    # resplandor suave detrás de la tele
    g = max(0, 1 - math.hypot(x - .5, y - .56) / .45)
    c = mix(c, (255, 255, 255), .10 * g * g)
    # antenas
    for bx in (.36, .66):
        if seg(x, y, .5, .30, bx, .12) < .016 or math.hypot(x - bx, y - .12) < .03:
            return WHITE
    # cuerpo y pantalla
    if rrect(x, y, .5, .57, .33, .25, .09) < 0:
        if rrect(x, y, .5, .57, .27, .19, .06) < 0:
            # brillo de cristal en la esquina superior
            sc = mix(SCREEN, (40, 44, 80), max(0, .5 - (x - .23) - (y - .38)) * .8)
            if tri(x, y, [(.45, .48), (.45, .66), (.60, .57)]):
                return LIME
            if math.hypot(x - .69, y - .44) < .028:
                return RED
            return sc
        return WHITE
    return c


def draw(n, ss=4):
    out = []
    for py in range(n):
        for px in range(n):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = color((px + (sx + .5) / ss) / n, (py + (sy + .5) / ss) / n)
                    for i in range(3):
                        acc[i] += c[i]
            out.extend(int(v / (ss * ss)) for v in acc)
    return out


for n in (180, 192, 512):
    png(f"site/icons/icon-{n}.png", n, n, draw(n))
print("ok")
