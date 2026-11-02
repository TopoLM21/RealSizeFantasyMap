"""Rebuild the bundled outline from a pinned game-map mirror (Pillow required).

Run: python tools/extract_coastline.py --tiles /path/to/tiles
Tiles are <x>/<y>.jpg from the -4 level in the source recorded below.
No original game textures are distributed with the app.
"""

import argparse
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "d522efa9bbd44894ccaef79731eb04a634d016d6"


def simplify(points, epsilon=0.9):
    if len(points) <= 2:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    distances = [abs(dx * (y1 - y) - (x1 - x) * dy) / length if length else
                 ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5 for x, y in points]
    idx = max(range(len(points)), key=distances.__getitem__)
    if distances[idx] <= epsilon:
        return [points[0], points[-1]]
    return simplify(points[:idx + 1], epsilon)[:-1] + simplify(points[idx:], epsilon)


def extract(tiles, output):
    source = Image.new("RGB", (1024, 1024), (0, 0, 0))
    hashes = {}
    for path in sorted(tiles.glob("*/*.jpg")):
        x, y = int(path.parent.name), int(path.stem)
        source.paste(Image.open(path), ((x + 2) * 256, (y + 1) * 256))
        hashes[str(path.relative_to(tiles))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(hashes) != 12:
        raise ValueError("Expected the 12 source tiles listed in SOURCES.md")
    mask = Image.new("L", source.size)
    mask.putdata([255 if ((r > b * .91 and g > b * 1.06) or
                         (r > 120 and g > 120 and b < r * 1.3)) else 0
                  for r, g, b in source.getdata()])
    mask = mask.filter(ImageFilter.MedianFilter(3)).filter(
        ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    w, h = mask.size
    pixels = mask.load()
    # Flood the external ocean. Enclosed inland water is filled: coastline only.
    ocean = {(0, 0)}
    queue = deque(ocean)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not pixels[nx, ny] and (nx, ny) not in ocean:
                ocean.add((nx, ny))
                queue.append((nx, ny))
    edges = defaultdict(list)
    for y in range(h):
        for x in range(w):
            if (x, y) in ocean:
                continue
            for neighbor, start, end in (
                ((x, y - 1), (x, y), (x + 1, y)),
                ((x + 1, y), (x + 1, y), (x + 1, y + 1)),
                ((x, y + 1), (x + 1, y + 1), (x, y + 1)),
                ((x - 1, y), (x, y + 1), (x, y)),
            ):
                if neighbor in ocean:
                    edges[start].append(end)
    polygons = []
    while edges:
        start = next(iter(edges))
        ring, p = [start], start
        while True:
            q = edges[p].pop()
            if not edges[p]:
                del edges[p]
            ring.append(q)
            p = q
            if p == start:
                break
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2
        if area >= 6:
            # Split the closed ring before RDP to avoid coincident endpoints.
            mid = len(ring) // 2
            polygons.append(simplify(ring[:mid + 1])[:-1] + simplify(ring[mid:]))
    minx = min(x for ring in polygons for x, _ in ring)
    maxx = max(x for ring in polygons for x, _ in ring)
    miny = min(y for ring in polygons for _, y in ring)
    maxy = max(y for ring in polygons for _, y in ring)
    unit = 20_000 / (maxx - minx)

    def project(point):
        x, y = point
        return [round((x - (maxx + minx) / 2) * unit, 3),
                round((y - (maxy + miny) / 2) * unit, 3)]

    # Mark clipped map edges separately; these are NOT known coastlines.
    rgb = source.load()
    frontiers = []
    for ring in polygons:
        for a, b in zip(ring, ring[1:]):
            x, y = int((a[0] + b[0]) / 2), int((a[1] + b[1]) / 2)
            if any(max(rgb[nx, ny]) < 15 for nx in range(max(0, x - 5), min(w, x + 6))
                   for ny in range(max(0, y - 5), min(h, y + 6))):
                frontiers.append([project(a), project(b)])
    result = {
        "version": 1, "title": "Тейват · снимок 4.0",
        "source": f"https://github.com/genshin-base/teyvat-map/tree/{COMMIT}",
        "note": "Упрощённая сегментация игровой карты 4.0; пунктир — край опубликованной карты, не берег.",
        "source_sha256": hashes, "width_km": 20000,
        "polygons": [[project(p) for p in ring] for ring in polygons],
        "frontiers": frontiers,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(polygons)} land polygons; {sum(map(len, result['polygons']))} vertices → {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data/coastline.json")
    args = parser.parse_args()
    extract(args.tiles, args.output)
