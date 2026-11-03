"""Export the same bounded visual smoothing used by the atlas (Pillow needed)."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coastline_style import smooth_coastline


def main():
    data = json.loads((ROOT / "data/coastline.json").read_text(encoding="utf-8"))
    polygons = smooth_coastline(data["polygons"], data["km_per_source_pixel"])
    unit = data["km_per_source_pixel"]
    x1, y1, x2, y2 = data["source_bounds_px"]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    pixel_rings = [[(x / unit + cx, y / unit + cy) for x, y in ring] for ring in polygons]
    paths = []
    for ring in pixel_rings:
        commands = "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in ring[:-1]) + " Z"
        paths.append(f'    <path d="{commands}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x1-15} {y1-15} {x2-x1+30} {y2-y1+30}">\n'
           '  <title>Тейват — сглаженная береговая линия</title>\n'
           '  <desc>Визуальное сглаживание с отклонением не более 0,45 пикселя исходника. '
           'Исходная геометрия и масштаб сохраняются отдельно.</desc>\n'
           '  <g fill="none" stroke="#172c36" stroke-width="1.2" stroke-linejoin="round">\n' +
           "\n".join(paths) + "\n  </g>\n</svg>\n")
    (ROOT / "data/coastline-smooth.svg").write_text(svg, encoding="utf-8")
    features = []
    for index, polygon in enumerate(polygons, 1):
        ring = [[round(x * .009, 7), round(-y * .009, 7)] for x, y in polygon]
        if sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:])) < 0:
            ring.reverse()
        features.append({"type": "Feature", "properties": {"land_component": index},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}})
    geojson = {"type": "FeatureCollection", "name": "Teyvat smoothed visual coastline",
               "source_sha256": data["source_sha256"], "max_deviation_source_px": .45,
               "description": "Fictional planet coordinates; visual smoothing, not Earth geography.",
               "features": features}
    (ROOT / "data/coastline-smooth.geojson").write_text(json.dumps(geojson, separators=(",", ":")) + "\n")

    def render(rings, box, zoom=1, samples=4):
        left, top, right, bottom = box
        width, height = round((right - left) * zoom), round((bottom - top) * zoom)
        image = Image.new("RGB", (width * samples, height * samples), "#142f40")
        draw = ImageDraw.Draw(image)
        for ring in rings:
            points = [((x / unit + cx - left) * zoom * samples,
                       (y / unit + cy - top) * zoom * samples) for x, y in ring]
            draw.polygon(points, fill="#34554f")
            draw.line(points, fill="#79ac94", width=max(1, round(1.2 * samples)), joint="curve")
        return image.resize((width, height), Image.Resampling.LANCZOS) if samples > 1 else image

    render(polygons, (x1-25, y1-25, x2+25, y2+25)).save(ROOT / "data/coastline-smooth-preview.png")
    box = (645, 485, 700, 540)
    old = render(data["polygons"], box, zoom=8, samples=1)
    new = render(polygons, box, zoom=8)
    comparison = Image.new("RGB", (old.width * 2, old.height))
    comparison.paste(old, (0, 0))
    comparison.paste(new, (old.width, 0))
    comparison.save(ROOT / "docs/smoothing-comparison.png")
    print(f"Exported {len(polygons)} smoothed coastlines; original data unchanged")


if __name__ == "__main__":
    main()
