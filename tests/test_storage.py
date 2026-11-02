import json
import tempfile
import unittest
from pathlib import Path

from storage import load_markers, save_markers, validate_markers


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.marker = {"id": "one", "name": "Порт Ли Юэ", "x": 1234.5, "y": -789.25}

    def test_portable_unicode_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/markers.json"
            save_markers(path, [self.marker])
            self.assertEqual(load_markers(path), [self.marker])
            self.assertIn("Порт", path.read_text(encoding="utf-8"))

    def test_invalid_save_keeps_previous_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "markers.json"
            save_markers(path, [self.marker])
            with self.assertRaises(ValueError):
                save_markers(path, [{**self.marker, "x": float("nan")}])
            self.assertEqual(load_markers(path), [self.marker])
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_rejects_malformed_imports(self):
        bad = [None, [], {}, {"version": 2, "markers": []},
               {"version": 1, "markers": [self.marker, self.marker]}]
        for field, value in [("x", True), ("x", "3"), ("x", 30_001), ("y", -10_001),
                             ("y", float("inf")), ("name", " "), ("name", "x" * 101),
                             ("id", "")]:
            bad.append({"version": 1, "markers": [{**self.marker, field: value}]})
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_markers(payload)

    def test_world_corners_and_empty_session(self):
        self.assertEqual(validate_markers({"version": 1, "markers": []}), [])
        validate_markers({"version": 1, "markers": [
            {**self.marker, "x": -10_000, "y": -10_000},
            {**self.marker, "id": "two", "x": 30_000, "y": 10_000}]})

    def test_coastline_fits_one_hemisphere(self):
        data = json.loads((Path(__file__).resolve().parents[1] / "data/coastline.json").read_text())
        points = [p for ring in data["polygons"] for p in ring]
        self.assertGreater(len(data["polygons"]), 10)
        self.assertEqual(max(p[0] for p in points) - min(p[0] for p in points), 20_000)
        self.assertTrue(all(-10_000 <= x <= 10_000 and -10_000 <= y <= 10_000 for x, y in points))


if __name__ == "__main__":
    unittest.main()
