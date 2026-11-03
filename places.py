"""A separate, explicitly approximate geographic place catalogue."""

import json
import math
import os
import tempfile
import unicodedata
from pathlib import Path

KINDS = {"city": "Город", "town": "Поселение", "port": "Порт", "landmark": "Место"}


def _read_catalog(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("places"), list):
        raise ValueError("Неизвестная версия или неверный формат каталога мест")
    ids = [item.get("id") if isinstance(item, dict) else None for item in data["places"]]
    if any(not isinstance(ident, str) or not ident for ident in ids) or len(set(ids)) != len(ids):
        raise ValueError("В каталоге должны быть уникальные непустые ID")
    if not isinstance(data.get("name_reference"), str):
        raise ValueError("В каталоге отсутствует источник названий")
    for item in data["places"]:
        if (not isinstance(item.get("name"), str) or not item["name"].strip() or
                not isinstance(item.get("region"), str) or item.get("kind") not in KINDS or
                not isinstance(item.get("aliases", []), list) or
                any(not isinstance(alias, str) for alias in item.get("aliases", []))):
            raise ValueError("Неверные название, регион, вид или алиасы места")
    return data


def project_source_point(point, coastline):
    if (not isinstance(point, (list, tuple)) or len(point) != 2 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)):
        raise ValueError("Неверные координаты места")
    x1, y1, x2, y2 = coastline["source_bounds_px"]
    unit = coastline["km_per_source_pixel"]
    x, y = (point[0] - (x1+x2)/2) * unit, (point[1] - (y1+y2)/2) * unit
    if not (-10_000-1e-7 <= x <= 30_000+1e-7 and -10_000-1e-7 <= y <= 10_000+1e-7):
        raise ValueError("Место за пределами проекции")
    return x, y


def set_place_source_point(place, point, coastline, accuracy="user_adjusted"):
    if point is None:
        place.update(source_pixel=None, x=None, y=None, position_accuracy="unplaced")
    else:
        x, y = project_source_point(point, coastline)
        place.update(source_pixel=list(point), x=x, y=y, position_accuracy=accuracy)


def move_place(place, x, y, coastline):
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)) or
            not (-10_000 <= x <= 30_000 and -10_000 <= y <= 10_000)):
        raise ValueError("Выберите точку внутри прямоугольника планеты")
    x1, y1, x2, y2 = coastline["source_bounds_px"]
    unit = coastline["km_per_source_pixel"]
    point = [round(x/unit + (x1+x2)/2, 4), round(y/unit + (y1+y2)/2, 4)]
    set_place_source_point(place, point, coastline)


def save_place_positions(path, coastline, changes, expected_positions=None):
    """Merge edited positions into the latest catalogue; preserve every other field.

    A concurrent change to an edited coordinate is rejected. Atomic replacement
    leaves the old file intact on validation, write or conflict failures.
    """
    path = Path(path)
    original = path.read_bytes()
    data = _read_catalog(path)
    for item in data["places"]:
        if item.get("source_pixel") is not None:
            project_source_point(item["source_pixel"], coastline)
    by_id = {p["id"]: p for p in data["places"]}
    for ident, change in changes.items():
        if ident not in by_id:
            raise ValueError(f"POI {ident} больше нет в файле. Перезапустите приложение перед правкой.")
        item = by_id[ident]
        if expected_positions is not None and item.get("source_pixel") != expected_positions.get(ident):
            raise ValueError(f"Координаты «{item.get('name', ident)}» изменены вне приложения. "
                             "Сохранение отменено, чтобы не затереть чужую правку.")
        point = change["source_pixel"]
        if point is not None:
            project_source_point(point, coastline)
        accuracy = change.get("position_accuracy", "user_adjusted") if point is not None else "unplaced"
        if accuracy not in {"approximate", "user_adjusted", "unplaced"}:
            raise ValueError("Неверный статус привязки")
        item["source_pixel"] = list(point) if point is not None else None
        item["position_accuracy"] = accuracy
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
        if path.read_bytes() != original:
            raise ValueError("Каталог изменился во время сохранения. Повторите после проверки файла.")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold().replace("ё", "е"))
                   if not unicodedata.combining(c))


def load_places(path, coastline):
    data = _read_catalog(path)
    seen, result = set(), []
    for item in data["places"]:
        ident = item["id"]
        if ident in seen or not ident or item["kind"] not in KINDS:
            raise ValueError("Неверный ID или вид места")
        seen.add(ident)
        place = dict(item)
        point = item.get("source_pixel")
        set_place_source_point(place, point, coastline, item.get("position_accuracy", "approximate"))
        place["source"] = item.get("source", data["name_reference"])
        place["search_text"] = normalize(" ".join([item["name"], item["region"],
                                                   *item.get("aliases", [])]))
        result.append(place)
    return result


def search_places(places, query="", kind=None):
    words = normalize(query).split()
    return [p for p in places if (kind is None or p["kind"] == kind) and
            all(word in p["search_text"] for word in words)]
