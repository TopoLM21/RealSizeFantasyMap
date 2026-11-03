"""A separate, explicitly approximate geographic place catalogue."""

import json
import math
import unicodedata
from pathlib import Path

KINDS = {"city": "Город", "town": "Поселение", "port": "Порт", "landmark": "Место"}


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold().replace("ё", "е"))
                   if not unicodedata.combining(c))


def load_places(path, coastline):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Неизвестная версия каталога мест")
    x1, y1, x2, y2 = coastline["source_bounds_px"]
    unit = coastline["km_per_source_pixel"]
    seen, result = set(), []
    for item in data["places"]:
        ident = item["id"]
        if ident in seen or not ident or item["kind"] not in KINDS:
            raise ValueError("Неверный ID или вид места")
        seen.add(ident)
        place = dict(item)
        point = item.get("source_pixel")
        place["x"] = place["y"] = None
        if point is not None:
            px, py = point
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point):
                raise ValueError("Неверные координаты места")
            x = (px - (x1 + x2) / 2) * unit
            y = (py - (y1 + y2) / 2) * unit
            if not (-10_000 <= x <= 30_000 and -10_000 <= y <= 10_000):
                raise ValueError("Место за пределами проекции")
            place.update(x=x, y=y)
        place["source"] = item.get("source", data["name_reference"])
        place["position_accuracy"] = "unplaced" if point is None else "approximate"
        place["search_text"] = normalize(" ".join([item["name"], item["region"],
                                                   *item.get("aliases", [])]))
        result.append(place)
    return result


def search_places(places, query="", kind=None):
    words = normalize(query).split()
    return [p for p in places if (kind is None or p["kind"] == kind) and
            all(word in p["search_text"] for word in words)]
