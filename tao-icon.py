#!/usr/bin/env python3
"""Ve yap_icon.ico — cung ngon ngu thi giac voi thanh song trong app.

Ve o 1024px roi thu nho: cac canh cong va dau bo tron moi min o 16px.
Chay:  py tao-icon.py
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
OUT = HERE / "yap_icon.ico"
S = 1024

BG_TOP = (18, 42, 52)
BG_BOT = (6, 16, 24)
RIM = (44, 122, 134)
GLOW = (28, 150, 160)
CORE_HI = (170, 255, 248)
CORE_LO = (79, 228, 222)

# Chieu cao tuong doi cua tung cot, doi xung quanh truc giua.
BARS = [0.22, 0.42, 0.68, 0.95, 0.72, 0.46, 0.26]


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=radius, fill=255)
    return m


def build():
    # Nen: chuyen mau doc, toi dan xuong duoi
    bg = Image.new("RGB", (S, S), BG_BOT)
    d = ImageDraw.Draw(bg)
    for y in range(S):
        t = y / float(S - 1)
        d.line([(0, y), (S, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t)
                          for i in range(3)))

    # Song: ve rieng ra roi lam nhoe de tao quang sang
    glow = Image.new("RGB", (S, S), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    core = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(core)

    n = len(BARS)
    step = S * 0.115
    w = S * 0.052
    cx, cy = S / 2.0, S / 2.0
    x0 = cx - step * (n - 1) / 2.0

    for i, h in enumerate(BARS):
        x = x0 + i * step
        half = h * S * 0.30
        box = [x - w / 2, cy - half, x + w / 2, cy + half]
        gd.rounded_rectangle(box, radius=w / 2, fill=GLOW)
        # Cot cang cao cang sang
        col = tuple(int(CORE_LO[k] + (CORE_HI[k] - CORE_LO[k]) * h)
                    for k in range(3))
        cd.rounded_rectangle(box, radius=w / 2, fill=col + (255,))

    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.035))
    img = Image.blend(bg, Image.blend(bg, glow, 0.0), 0.0)
    img = Image.composite(glow, bg, glow.convert("L").point(lambda v: min(255, v * 3)))
    img = Image.blend(bg, img, 0.85)
    img = img.convert("RGBA")
    img.alpha_composite(core)

    # Vien sang mong o mep
    ImageDraw.Draw(img).rounded_rectangle(
        [6, 6, S - 7, S - 7], radius=int(S * 0.235), outline=RIM + (255,),
        width=int(S * 0.012))

    img.putalpha(rounded_mask(S, int(S * 0.235)))

    sizes = [256, 128, 64, 48, 32, 24, 16]
    frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(OUT, format="ICO",
                   sizes=[(s, s) for s in sizes], append_images=frames[1:])
    print("da ve: %s" % OUT)
    png = HERE / "yap_icon_preview.png"
    img.resize((256, 256), Image.LANCZOS).save(png)
    print("xem thu : %s" % png)


if __name__ == "__main__":
    build()
