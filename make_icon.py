#!/usr/bin/env python3
# Eclipse Gig Core MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Generate icon-512.png — brand §6: eclipse motif on navy (#0d1b2a),

"""Generate icon-512.png — brand §6: eclipse motif on navy (#0d1b2a),
one per-product glyph. Gig Core's glyph is the Task Brief itself: a
document with scope lines and a hash seal, inside the gradient
eclipse ring. PIL only; deterministic."""
from PIL import Image, ImageDraw

S = 512
NAVY = (13, 27, 42, 255)
STOPS = [(15, 246, 247), (0, 212, 255), (123, 44, 191)]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def grad(t):
    return lerp(STOPS[0], STOPS[1], t * 2) if t < 0.5 else \
        lerp(STOPS[1], STOPS[2], (t - 0.5) * 2)


def main():
    img = Image.new("RGBA", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    ring = [54, 54, 458, 458]
    for i in range(72):
        t = i / 72
        d.arc(ring, start=i * 5, end=i * 5 + 6, fill=grad(t), width=13)
    d.ellipse([126, 126, 386, 386], fill=NAVY)
    # The brief: a document.
    doc = [176, 130, 336, 382]
    d.rounded_rectangle(doc, radius=14, fill=(8, 12, 20, 255),
                        outline=(254, 254, 254, 255), width=6)
    # Scope lines.
    for i, y in enumerate((176, 216, 256)):
        d.line([(204, y), (308, y)], fill=grad(0.2 + 0.2 * i), width=9)
    # Two scope check marks.
    for y in (296, 336):
        d.line([(204, y + 6), (216, y + 16)], fill=grad(0.55), width=6)
        d.line([(216, y + 16), (238, y - 6)], fill=grad(0.55), width=6)
        d.line([(252, y + 4), (308, y + 4)],
               fill=(160, 174, 192, 255), width=7)
    # Hash seal at the document's foot.
    d.ellipse([292, 330, 330, 368], fill=grad(0.85))
    img.save("icon-512.png")
    print("wrote icon-512.png", img.size, img.mode)


if __name__ == "__main__":
    main()

# Eclipse Gig Core MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
