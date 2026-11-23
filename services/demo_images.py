import math
import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

PALETTES = [
    dict(wall=(244, 232, 214), wall2=(232, 214, 190), floor=(176, 132, 96), accent=(46, 139, 132), bed=(236, 240, 245), sky=(160, 205, 235)),
    dict(wall=(226, 236, 244), wall2=(204, 222, 238), floor=(196, 160, 122), accent=(230, 126, 84), bed=(250, 244, 236), sky=(190, 225, 245)),
    dict(wall=(240, 236, 246), wall2=(222, 214, 238), floor=(150, 118, 98), accent=(120, 94, 186), bed=(238, 232, 245), sky=(175, 200, 240)),
    dict(wall=(232, 244, 236), wall2=(208, 230, 214), floor=(186, 150, 110), accent=(214, 96, 96), bed=(248, 248, 240), sky=(170, 220, 230)),
    dict(wall=(248, 238, 228), wall2=(240, 218, 200), floor=(158, 120, 90), accent=(52, 120, 170), bed=(236, 242, 248), sky=(180, 214, 240)),
]

def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

PW, PH = 2048, 1024
ROOM_D, CEIL_H, CAM_H = 2.0, 1.0, 1.4
PX_PER_RAD = PH / math.pi

def _proj(wall, u, z):
    az = math.atan2(u, ROOM_D)
    x = (wall * PW / 4 + PW / 8 + az / (2 * math.pi) * PW) % PW
    y = PH / 2 - math.atan2(z, math.hypot(ROOM_D, u)) * PX_PER_RAD
    return x, y


def _quad(draw, wall, u0, u1, z0, z1, fill, outline=None, steps=10):
    pts = []
    for i in range(steps + 1):
        pts.append(_proj(wall, u0 + (u1 - u0) * i / steps, z1))
    for i in range(steps + 1):
        pts.append(_proj(wall, u1 - (u1 - u0) * i / steps, z0))
    draw.polygon(pts, fill=fill, outline=outline)


def panorama_image(palette_index, seed=0):
    rnd = random.Random(palette_index * 31 + seed)
    pal = PALETTES[palette_index % len(PALETTES)]
    img = Image.new("RGB", (PW, PH), (255, 255, 255))
    d = ImageDraw.Draw(img)
    wall_tones = [_lerp(pal["wall"], (255, 255, 255), 0.12), pal["wall"], _lerp(pal["wall"], pal["wall2"], 0.7), pal["wall2"]]
    for x in range(PW):
        wall = int(x / (PW / 4)) % 4
        local = (x % (PW / 4)) / (PW / 4)
        u = (local - 0.5) * 2 * ROOM_D
        dist = math.hypot(ROOM_D, u)
        top = PH / 2 - math.atan2(CEIL_H, dist) * PX_PER_RAD
        bottom = PH / 2 + math.atan2(CAM_H, dist) * PX_PER_RAD
        shade = 1 - 0.1 * abs(local - 0.5) * 2
        d.line((x, 0, x, top), fill=_lerp((250, 250, 252), (232, 234, 240), top / (PH / 2)))
        d.line((x, top, x, bottom), fill=tuple(int(c * shade) for c in wall_tones[wall]))
        stripe = int((x / 18) + (bottom * 0)) % 2
        floor_base = pal["floor"]
        for y0 in range(int(bottom), PH, 6):
            f = _lerp(floor_base, tuple(int(c * 0.7) for c in floor_base), (y0 - bottom) / max(PH - bottom, 1))
            d.line((x, y0, x, y0 + 5), fill=f)
        d.line((x, bottom - 6, x, bottom), fill=(250, 248, 244))
    for wall in range(4):
        x = wall * PW / 4
        d.line((x, 0, x, PH), fill=(150, 140, 130), width=1)

    _quad(d, 0, -0.9, 0.9, -0.1, 0.75, (250, 250, 250))
    _quad(d, 0, -0.82, 0.82, -0.02, 0.67, pal["sky"])
    _quad(d, 0, -0.03, 0.03, -0.02, 0.67, (250, 250, 250))
    _quad(d, 0, -0.82, 0.82, 0.31, 0.35, (250, 250, 250))
    _quad(d, 1, -0.5, 0.5, -1.4, 0.55, (140, 100, 70))
    _quad(d, 1, -0.44, 0.44, -1.38, 0.5, (170, 128, 92))
    _quad(d, 2, -1.1, 1.1, -1.4, -0.45, _lerp(pal["accent"], (60, 50, 50), 0.4))
    _quad(d, 2, -1.1, 1.1, -1.4, -0.85, pal["bed"])
    _quad(d, 2, -1.1, 1.1, -1.4, -1.0, pal["accent"])
    _quad(d, 2, -0.95, -0.2, -0.88, -0.7, (255, 255, 255))
    _quad(d, 2, 0.2, 0.95, -0.88, -0.7, (255, 255, 255))
    for i in range(3):
        _quad(d, 2, -0.5 + i * 0.4, -0.2 + i * 0.4, 0.05, 0.4, _lerp(pal["accent"], (255, 255, 255), 0.25 * i))
    _quad(d, 3, -1.3, -0.1, -0.7, -0.62, (158, 118, 84))
    _quad(d, 3, -1.25, -1.15, -1.4, -0.7, (130, 96, 68))
    _quad(d, 3, -0.2, -0.1, -1.4, -0.7, (130, 96, 68))
    _quad(d, 3, -1.0, -0.4, -0.62, -0.1, (60, 66, 80))
    _quad(d, 3, 0.4, 1.4, -1.4, 0.7, (150, 112, 80))
    for row in range(5):
        z0 = -1.35 + row * 0.42
        _quad(d, 3, 0.45, 1.35, z0, z0 + 0.04, (110, 80, 56))
        u = 0.5
        while u < 1.3:
            bw = rnd.uniform(0.05, 0.1)
            col = _lerp(pal["accent"], (rnd.randint(60, 240),) * 3, rnd.random() * 0.8)
            _quad(d, 3, u, u + bw, z0 + 0.05, z0 + 0.05 + rnd.uniform(0.22, 0.34), col, steps=3)
            u += bw + 0.01
    out = BytesIO()
    img.filter(ImageFilter.GaussianBlur(0.7)).save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue()

