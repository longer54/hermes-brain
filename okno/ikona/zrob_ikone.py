#!/usr/bin/env python3
"""Ikona Mózgu Hermesa: prosta świecąca kula z pierścieniem (rysowana, bez obcych grafik), 8 rozmiarów."""
import os
from PIL import Image, ImageDraw, ImageFilter

TU = os.path.dirname(os.path.abspath(__file__))
S = 512
out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(out)
for i in range(240, 0, -2):  # radial gradient: white core -> blue -> navy
    t = i / 240
    col = (int(255 * (1 - t) + 20 * t), int(255 * (1 - t) + 90 * t), int(255 * (1 - t) + 200 * t), 255)
    c = (S // 2 - int(30 * (1 - t)), S // 2 - int(40 * (1 - t)))
    d.ellipse((c[0] - i, c[1] - i, c[0] + i, c[1] + i), fill=col)
ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(ring).ellipse((24, 24, S - 24, S - 24), outline=(120, 220, 255, 255), width=16)
out = Image.alpha_composite(ring.filter(ImageFilter.GaussianBlur(6)), out)
out = Image.alpha_composite(out, ring)
for r in (16, 22, 24, 32, 48, 64, 128, 256):
    out.resize((r, r), Image.LANCZOS).save(os.path.join(TU, f"mozg-{r}.png"))
print("ok")
