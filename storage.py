"""Validated portable markers; atomic saves never truncate the previous file."""

import json
import math
import os
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1


def validate_markers(payload):
    if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION:
        raise ValueError("Неизвестная версия файла меток")
    markers = payload.get("markers")
    if not isinstance(markers, list) or len(markers) > 1000:
        raise ValueError("Ожидается список не более чем из 1000 меток")
    result, ids = [], set()
    for m in markers:
        if not isinstance(m, dict):
            raise ValueError("Неверный формат метки")
        ident, name = m.get("id"), m.get("name")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("У меток должны быть уникальные непустые ID")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Название метки должно содержать от 1 до 100 символов")
        x, y = m.get("x"), m.get("y")
        if any(isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n)
               for n in (x, y)):
            raise ValueError("Координаты должны быть конечными числами")
        if not (-10_000 <= x <= 30_000 and -10_000 <= y <= 10_000):
            raise ValueError("Метка находится за пределами планеты")
        ids.add(ident)
        result.append({"id": ident, "name": name.strip(), "x": float(x), "y": float(y)})
    return result


def load_markers(path):
    with Path(path).open(encoding="utf-8") as f:
        return validate_markers(json.load(f))


def save_markers(path, markers):
    payload = {"version": SCHEMA_VERSION, "markers": markers}
    validate_markers(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
