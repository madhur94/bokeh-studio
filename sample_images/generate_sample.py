"""Recreate the bundled original synthetic scene; no downloads or third-party art."""
from pathlib import Path
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def make_sample(directory: Path) -> None:
    width, height = 1200, 780
    y, x = np.mgrid[:height, :width]
    light = np.clip(1 - np.sqrt(((x - 800) / 1100) ** 2 + ((y - 240) / 950) ** 2), 0, 1)
    wall = np.stack([43 + 53 * light, 56 + 56 * light, 42 + 39 * light], axis=-1).astype(np.uint8)
    image = Image.fromarray(wall)
    depth = Image.new("L", (width, height), 0)
    draw, dd = ImageDraw.Draw(image), ImageDraw.Draw(depth)
    # Architectural lines and a distant, textured book stack make defocus easy to see.
    for xx in range(50, width, 100):
        draw.line((xx, 0, xx, 575), fill=(84, 100, 71), width=2)
    draw.rectangle((0, 575, width, height), fill=(125, 117, 88))
    dd.rectangle((0, 575, width, height), fill=45)
    for yy in range(590, height, 18):
        draw.line((0, yy, width, yy), fill=(137, 128, 95), width=1)
    for index, color in enumerate([(194, 176, 130), (61, 79, 60), (164, 148, 108)]):
        top = 525 - index * 36
        draw.rounded_rectangle((800 + index * 8, top, 1100 - index * 10, top + 32), radius=4, fill=color)
        dd.rectangle((800 + index * 8, top, 1100 - index * 10, top + 32), fill=65)
        for line in range(top + 4, top + 29, 5):
            draw.line((820, line, 1080 - index * 10, line), fill=(110, 108, 83), width=1)
    # Small high-contrast lights sit on the far wall.
    for xx, yy, radius in [(240, 140, 7), (980, 180, 9), (850, 340, 5), (150, 395, 6)]:
        draw.ellipse((xx-radius, yy-radius, xx+radius, yy+radius), fill=(246, 228, 169))
    shadow = Image.new("RGBA", image.size)
    ImageDraw.Draw(shadow).ellipse((290, 636, 765, 705), fill=(10, 17, 10, 150))
    image = Image.alpha_composite(image.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(16))).convert("RGB")
    draw = ImageDraw.Draw(image)
    # Foreground plant and ceramic vase share one true depth plane (near = .22).
    near = 199
    for endx, endy in [(315, 230), (620, 160), (465, 130), (720, 295), (305, 360), (650, 390)]:
        draw.line((515, 530, endx, endy), fill=(59, 76, 39), width=7)
        dd.line((515, 530, endx, endy), fill=near, width=7)
        angle = math.atan2(endy - 530, endx - 515)
        cx, cy = endx, endy
        ux, uy = math.cos(angle), math.sin(angle)
        vx, vy = -uy, ux
        points = [(cx + 80*ux, cy + 80*uy), (cx + 44*vx, cy + 44*vy),
                  (cx - 55*ux, cy - 55*uy), (cx - 44*vx, cy - 44*vy)]
        draw.polygon(points, fill=(118, 146, 76))
        dd.polygon(points, fill=near)
        draw.line((cx-45*ux, cy-45*uy, cx+68*ux, cy+68*uy), fill=(175, 190, 112), width=2)
    vase = [(450, 465), (574, 465), (579, 520), (628, 590), (620, 653), (590, 677),
            (430, 677), (405, 650), (398, 590), (447, 520)]
    draw.polygon(vase, fill=(198, 153, 104))
    dd.polygon(vase, fill=near)
    # Fine ceramic ribs provide visible in-focus detail.
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).polygon(vase, fill=255)
    ribs = image.copy()
    rd = ImageDraw.Draw(ribs)
    for xx in range(398, 630, 9):
        rd.line((xx, 470, xx, 680), fill=(167, 123, 81), width=2)
    image.paste(ribs, mask=mask)
    draw = ImageDraw.Draw(image)
    draw.ellipse((448, 455, 576, 478), fill=(98, 77, 50), outline=(215, 174, 122), width=5)
    dd.ellipse((448, 455, 576, 478), fill=near)
    # A close edge adds a near depth extremum and keeps normalization well defined.
    draw.rectangle((0, 758, width, height), fill=(92, 87, 65))
    dd.rectangle((0, 758, width, height), fill=255)
    directory.mkdir(parents=True, exist_ok=True)
    image.save(directory / "botanical_rgb.png")
    depth.save(directory / "botanical_depth.png")


if __name__ == "__main__":
    make_sample(Path(__file__).resolve().parent)
