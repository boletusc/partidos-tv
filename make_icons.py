"""Genera los iconos PNG de la app sin dependencias (campo de fútbol estilizado sobre fondo oscuro)."""
import math, struct, zlib
from pathlib import Path

def png(path, w, h, px):
    raw = b"".join(b"\x00" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def draw(n):
    ss = 3
    N = n * ss
    def inside(x, y):  # coordenadas normalizadas 0..1 → 0 fondo, 1 césped, 2 línea blanca
        cx, cy = x - .5, y - .5
        # pantalla de TV redondeada
        rx, ry, rr = .36, .27, .07
        dx, dy = max(abs(cx) - (rx - rr), 0), max(abs(cy + .02) - (ry - rr), 0)
        d = math.hypot(dx, dy) - rr
        if -0.028 < d < 0.0: return 2
        if d >= 0:
            return 0
        lw = .012
        r = math.hypot(cx, cy + .02)
        if abs(r - .1) < lw or abs(cx) < lw or r < .02: return 2
        return 1
    bg0, bg1 = (13, 17, 23), (22, 40, 30)
    grass = (31, 160, 90)
    out = []
    for py in range(n):
        for px_ in range(n):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    x, y = (px_ * ss + sx + .5) / N, (py * ss + sy + .5) / N
                    k = inside(x, y)
                    if k == 0:
                        t = y
                        c = tuple(int(bg0[i] + (bg1[i] - bg0[i]) * t) for i in range(3))
                    elif k == 1:
                        stripe = 1 if int((x - .14) / .09) % 2 else 0
                        c = tuple(min(255, v + 10 * stripe) for v in grass)
                    else:
                        c = (245, 248, 250)
                    for i in range(3): acc[i] += c[i]
            out.extend(v // (ss * ss) for v in acc)
    return out

for n in (180, 192, 512):
    png(f"site/icons/icon-{n}.png", n, n, draw(n))
print("ok")
