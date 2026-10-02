"""Draws the Windows installer splash image: the same screen as the update splash.

    uv run python ../packaging/splash.py OUT.png VERSION   (from backend/, which has Pillow)

Velopack shows the image at its size times the display scale, centred, and draws its progress
bar along the bottom edge. Keep the colours and geometry in step with SPLASH in desktop.py.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 360  # the update splash window
SS = 4  # supersampling, for smooth edges once scaled down
# The light theme of the app (index.css): --background, --foreground, --muted-foreground,
# --primary. Velopack shows no dark variant.
BG, FG, MUTE, TILE, GLYPH, EDGE = "#f9fafc", "#121b29", "#626a75", "#15284b", "#ffffff", "#e6e9ee"
# The app's Geist, once the interface is built (it ships in the static assets).
GEIST = sorted(
    (Path(__file__).parent.parent / "backend/src/binder/static/assets").glob(
        "geist-latin-wght-normal-*.woff2"
    )
)
PROGRESS_HEIGHT = 12  # Velopack's bar


def font(
    weight: int, names: tuple[str, ...], size: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in GEIST:
        try:
            geist = ImageFont.truetype(str(path), size * SS)
            geist.set_variation_by_axes([weight])
            return geist
        except OSError:
            continue
    # Segoe UI: what system-ui resolves to in the update splash without Geist.
    for name in names:
        try:
            return ImageFont.truetype(name, size * SS)
        except OSError:
            continue
    return ImageFont.load_default(size * SS)


def draw(version: str) -> Image.Image:
    image = Image.new("RGB", (WIDTH * SS, HEIGHT * SS), BG)
    d = ImageDraw.Draw(image)
    # Hairline edge, as in the update splash: a light window on a light desktop.
    d.rectangle((0, 0, WIDTH * SS - 1, HEIGHT * SS - 1), outline=EDGE, width=SS)

    # Logo: the 32-unit SVG of the update splash, 60 px wide, 80 px from the top.
    unit = 60 / 32 * SS
    ox, oy = (WIDTH * SS - 32 * unit) / 2, 80 * SS

    def box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        return (ox + x * unit, oy + y * unit, ox + (x + w) * unit, oy + (y + h) * unit)

    d.rounded_rectangle(box(0, 0, 32, 32), radius=8 * unit, fill=TILE)
    # The binder: its spine, the hinge, then four card sleeves.
    d.rounded_rectangle(box(8, 6, 16, 20), radius=2.2 * unit, fill=GLYPH)
    d.rectangle(box(11, 6, 1.1, 20), fill=TILE)
    for x in (13.6, 18.6):
        for y in (10, 16.6):
            d.rounded_rectangle(box(x, y, 3.8, 5.4), radius=0.6 * unit, fill=TILE)

    centre = WIDTH * SS / 2
    # Title: 20 px semibold, 16 px under the logo, 28 px line box.
    title = font(600, ("seguisb.ttf", "segoeuisb.ttf", "DejaVuSans-Bold.ttf"), 20)
    d.text((centre, (140 + 16 + 14) * SS), "Binder", font=title, fill=FG, anchor="mm")
    # Version, as in the update splash footer, just above the progress bar.
    small = font(400, ("segoeui.ttf", "DejaVuSans.ttf"), 11)
    d.text(
        (centre, (HEIGHT - PROGRESS_HEIGHT - 22) * SS),
        f"Version {version}",
        font=small,
        fill=MUTE,
        anchor="mm",
    )

    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    out, version = Path(sys.argv[1]), sys.argv[2]
    out.parent.mkdir(parents=True, exist_ok=True)
    draw(version).save(out)
