"""Extract vector land outlines from supplied line art or a textured blue map.

This is a deterministic measurement of source pixels. The profile records crop,
color/ink thresholds, any reviewed corrections and the source checksum.
Preparation only: Pillow, NumPy and SciPy. The atlas itself needs none of these.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

try:
    from .extract_coastline import simplify
except ImportError:
    from extract_coastline import simplify

ROOT = Path(__file__).resolve().parents[1]


def segment(source, profile):
    """Fill land while preserving the source's separations between closed regions."""
    if list(source.size) != profile["image_size"]:
        raise ValueError("Размер изображения не соответствует профилю обработки")
    # Transparent pixels often have black hidden RGB values. Composite first so
    # RGBA, LA and indexed PNG transparency behave like ink on white paper.
    source = Image.alpha_composite(Image.new("RGBA", source.size, "white"),
                                   source.convert("RGBA")).convert("RGB")
    valid = np.zeros((source.height, source.width), dtype=bool)
    x1, y1, x2, y2 = profile["crop"]
    valid[y1:y2, x1:x2] = True
    for x1, y1, x2, y2 in profile.get("exclude_rectangles", []):
        valid[y1:y2, x1:x2] = False
    mode = profile.get("mode", "color")
    if mode == "line_art":
        ink = (np.asarray(source.convert("L")) < profile["ink_threshold"]) & valid
        # Only white regions enclosed by the drawing are land. Adding the ink to
        # their interiors would merge islands sharing a thin drawn boundary.
        white_regions, _ = ndi.label(~ink)
        outside = np.unique(np.concatenate((white_regions[0], white_regions[-1],
                                            white_regions[:, 0], white_regions[:, -1])))
        mask = (white_regions > 0) & ~np.isin(white_regions, outside) & valid
    elif mode == "color":
        rgb = np.asarray(source.convert("RGB"), dtype=np.float64)
        red, green, blue = np.moveaxis(rgb, 2, 0)
        mask = ((red > blue * profile["red_blue_ratio"]) &
                (green > blue * profile["green_blue_ratio"]) & valid)
    else:
        raise ValueError(f"Неизвестный режим выделения: {mode}")
    radius = profile.get("closing_radius_px", 0)
    if radius:
        if mode == "line_art":
            raise ValueError("Для чистого рисунка замыкание отключено, чтобы не соединять острова")
        yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
        mask = ndi.binary_closing(mask, structure=xx * xx + yy * yy <= radius * radius)
    cuts = Image.new("1", source.size)
    draw = ImageDraw.Draw(cuts)
    for cut in profile.get("water_cuts", []):
        draw.line([tuple(p) for p in cut["points"]], fill=1, width=cut["width_px"])
    mask &= ~np.asarray(cuts)
    # The app requests coastlines only. Inland lakes and terrain lines disappear.
    mask = ndi.binary_fill_holes(mask)
    labels, _ = ndi.label(mask)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return sizes[labels] >= profile["minimum_land_area_px"]


def trace_rings(mask, tolerance):
    """Trace clockwise pixel edges, resolving shared corners by a right-hand turn."""
    padded = np.pad(mask, 1)
    edges = defaultdict(list)
    for y, x in zip(*np.where(mask)):
        x, y = int(x), int(y)
        for empty, a, b in (
            (not padded[y, x + 1], (x, y), (x + 1, y)),
            (not padded[y + 1, x + 2], (x + 1, y), (x + 1, y + 1)),
            (not padded[y + 2, x + 1], (x + 1, y + 1), (x, y + 1)),
            (not padded[y + 1, x], (x, y + 1), (x, y)),
        ):
            if empty:
                edges[a].append(b)
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    preference = {1: 0, 0: 1, 3: 2, 2: 3}
    rings = []
    while edges:
        start = next(iter(edges))
        ring, point, heading = [start], start, 0
        while True:
            candidates = edges[point]
            end = min(candidates, key=lambda p: preference[(directions[
                (p[0] - point[0], p[1] - point[1])] - heading) % 4])
            candidates.remove(end)
            if not candidates:
                del edges[point]
            heading = directions[(end[0] - point[0], end[1] - point[1])]
            point = end
            ring.append(point)
            if point == start:
                break
        if len(ring) >= 4:
            mid = len(ring) // 2
            ring = simplify(ring[:mid + 1], tolerance)[:-1] + simplify(ring[mid:], tolerance)
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def build_data(rings, profile, source_hash):
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    if not xs or max(xs) == min(xs):
        raise ValueError("На изображении не найдена суша")
    bounds = [min(xs), min(ys), max(xs), max(ys)]
    cx, cy = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    unit = profile["width_km"] / (bounds[2] - bounds[0])

    def project(point):
        return [round((point[0] - cx) * unit, 3), round((point[1] - cy) * unit, 3)]

    polygons = [[project(p) for p in ring] for ring in rings]
    if any(abs(y) > 10_000 for ring in polygons for _, y in ring):
        raise ValueError("Высота карты не помещается в выбранное полушарие")
    return {
        "version": 1, "map_id": "user-map-" + source_hash[:12],
        "title": "Тейват · карта пользователя",
        "subtitle": profile.get("subtitle", "Ваша карта · только суша и океан"),
        "source": profile.get("source_description",
            "Предоставленное пользователем изображение 1024×1024; версия игры не установлена"),
        "source_sha256": source_hash,
        "note": profile.get("note", "Приближённая векторизация изображения по параметрам профиля. "
                            "Актуальность и официальный статус исходника независимо не проверялись."),
        "width_km": profile["width_km"], "source_bounds_px": bounds,
        "km_per_source_pixel": unit, "polygons": polygons, "frontiers": [],
        "region_labels": [[name, *project((x, y))] for name, x, y in profile["region_labels_px"]],
        "demo_markers": [[name, *project((x, y))] for name, x, y in profile["demo_markers_px"]],
        "processing": {"mode": profile.get("mode", "color"),
                       "ink_threshold": profile.get("ink_threshold"),
                       "minimum_land_area_px": profile["minimum_land_area_px"],
                       "simplify_tolerance_px": profile["simplify_tolerance_px"],
                       "closing_radius_px": profile.get("closing_radius_px", 0),
                       "reviewed_water_cut_count": len(profile.get("water_cuts", []))},
    }


def write_artifacts(rings, mask, data, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "coastline.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    Image.fromarray(np.uint8(mask * 255)).save(directory / "coastline-mask.png")
    # SVG retains source pixel coordinates, so it can be overlaid on the original.
    x1, y1, x2, y2 = data["source_bounds_px"]
    paths = []
    for ring in rings:
        commands = "M " + " L ".join(f"{x},{y}" for x, y in ring[:-1]) + " Z"
        paths.append(f'    <path d="{commands}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x1 - 15} {y1 - 15} '
           f'{x2 - x1 + 30} {y2 - y1 + 30}">\n'
           '  <title>Береговая линия по предоставленной карте Тейвата</title>\n'
           f'  <desc>{escape(data["note"])}</desc>\n'
           '  <g fill="none" stroke="#172c36" stroke-width="1.2" stroke-linejoin="round">\n' +
           "\n".join(paths) + '\n  </g>\n</svg>\n')
    (directory / "coastline.svg").write_text(svg, encoding="utf-8")
    features = []
    for index, polygon in enumerate(data["polygons"], 1):
        ring = [[round(x * 360 / 40_000, 7), round(-y * 360 / 40_000, 7)] for x, y in polygon]
        # RFC 7946 outer rings use counterclockwise winding in lon/lat.
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
        if area < 0:
            ring.reverse()
        features.append({"type": "Feature", "properties": {"land_component": index},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}})
    geojson = {"type": "FeatureCollection", "name": "Teyvat derived coastline",
               "description": "Fictional planet coordinates, not real Earth locations. "
                              "Distances use a sphere of circumference 40000 km, not WGS84.",
               "features": features}
    (directory / "coastline.geojson").write_text(json.dumps(geojson, ensure_ascii=False,
        separators=(",", ":")) + "\n", encoding="utf-8")
    # Standalone inspection plot of the extracted data, with no source texture.
    preview = Image.new("RGB", mask.shape[::-1], "#142f40")
    draw = ImageDraw.Draw(preview)
    for ring in rings:
        draw.polygon(ring, fill="#42645b")
        draw.line(ring, fill="#a4d0b0", width=1)
    preview = preview.crop((x1 - 25, y1 - 25, x2 + 25, y2 + 25))
    preview.save(directory / "coastline-preview.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--profile", type=Path, default=ROOT / "data/user-map-profile.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(args.image.read_bytes()).hexdigest()
    if source_hash != profile["source_sha256"]:
        parser.error("SHA-256 изображения не совпадает с профилем. Для другого изображения нужен свой профиль.")
    with Image.open(args.image) as source:
        mask = segment(source, profile)
    rings = trace_rings(mask, profile["simplify_tolerance_px"])
    data = build_data(rings, profile, source_hash)
    write_artifacts(rings, mask, data, args.output_dir)
    print(f"{len(rings)} контуров; {sum(map(len, rings))} вершин; "
          f"{data['km_per_source_pixel']:.2f} км/пиксель → {args.output_dir}")


if __name__ == "__main__":
    main()
