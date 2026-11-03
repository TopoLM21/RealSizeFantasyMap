import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from places import load_places, search_places, move_place, save_place_positions

ROOT = Path(__file__).resolve().parents[1]


class PlacesTests(unittest.TestCase):
    def setUp(self):
        self.coast = json.loads((ROOT / "data/coastline.json").read_text())
        self.places = load_places(ROOT / "data/places.json", self.coast)

    def test_search_supports_alias_region_and_category(self):
        self.assertEqual(search_places(self.places, "Liyue Harbor")[0]["id"], "liyue-harbor")
        ports = search_places(self.places, "Сумеру", "port")
        self.assertTrue(ports)
        self.assertTrue(all(p["region"] == "Сумеру" and p["kind"] == "port" for p in ports))
        self.assertFalse(search_places(self.places, "несуществующее место"))

    def test_unplaced_names_never_gain_fabricated_coordinates(self):
        unplaced = [p for p in self.places if p["source_pixel"] is None]
        self.assertTrue(all(p["x"] is None and p["y"] is None for p in unplaced))
        self.assertTrue(all(p["source"].startswith("https://") for p in unplaced))

    def test_place_projection_roundtrip_uses_catalog_coordinates(self):
        point = next(p for p in self.places if p["id"] == "mondstadt")
        x1, y1, x2, y2 = self.coast["source_bounds_px"]
        unit = self.coast["km_per_source_pixel"]
        self.assertAlmostEqual(point["x"]/unit + (x1+x2)/2, point["source_pixel"][0])
        self.assertAlmostEqual(point["y"]/unit + (y1+y2)/2, point["source_pixel"][1])


class PlaceEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "places.json"
        self.data = json.loads((ROOT / "data/places.json").read_text(encoding="utf-8"))
        # Stable fixture: contributors are expected to change the real catalogue.
        self.data["places"][0]["source_pixel"] = [731, 465]
        self.data["custom_note"] = "Сохранить эту метаинформацию"
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.coast = json.loads((ROOT / "data/coastline.json").read_text())
        self.before = self.path.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_project_file_roundtrip_preserves_names_aliases_and_metadata(self):
        point = load_places(self.path, self.coast)[0]
        move_place(point, point["x"] + 500, point["y"] + 250, self.coast)
        change = {"source_pixel": point["source_pixel"], "position_accuracy": point["position_accuracy"]}
        save_place_positions(self.path, self.coast, {point["id"]: change},
                             {point["id"]: self.data["places"][0]["source_pixel"]})
        after = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(after["custom_note"], self.data["custom_note"])
        self.assertEqual(after["places"][1:], self.data["places"][1:])
        self.assertEqual(after["places"][0]["aliases"], self.data["places"][0]["aliases"])
        reloaded = load_places(self.path, self.coast)[0]
        self.assertEqual(reloaded["position_accuracy"], "user_adjusted")
        self.assertEqual(reloaded["source_pixel"], point["source_pixel"])
        self.assertAlmostEqual(reloaded["x"], point["x"])

    def test_invalid_positions_never_modify_the_project_file(self):
        for point in [[True, 465], [float("nan"), 465], [731], [2000, 465], [731, -1000]]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                save_place_positions(self.path, self.coast, {"mondstadt": {"source_pixel": point}})
            self.assertEqual(self.path.read_bytes(), self.before)

    def test_external_metadata_and_other_positions_are_preserved(self):
        changed = json.loads(self.path.read_text(encoding="utf-8"))
        changed["places"][1]["source_pixel"] = [680, 550]
        changed["places"][0]["description"] = "Внешняя правка описания"
        self.path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        save_place_positions(self.path, self.coast, {"mondstadt": {"source_pixel": [735, 465]}},
                             {"mondstadt": [731, 465]})
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["places"][1]["source_pixel"], [680, 550])
        self.assertEqual(saved["places"][0]["description"], "Внешняя правка описания")

    def test_conflicting_external_position_is_not_overwritten(self):
        changed = json.loads(self.path.read_text(encoding="utf-8"))
        changed["places"][0]["source_pixel"] = [739, 467]
        self.path.write_text(json.dumps(changed), encoding="utf-8")
        external = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "изменены вне приложения"):
            save_place_positions(self.path, self.coast, {"mondstadt": {"source_pixel": [740, 468]}},
                                 {"mondstadt": [731, 465]})
        self.assertEqual(self.path.read_bytes(), external)

    def test_failed_replace_leaves_original_and_no_temporary_file(self):
        with patch("places.os.replace", side_effect=OSError("disk error")), self.assertRaises(OSError):
            save_place_positions(self.path, self.coast, {"mondstadt": {"source_pixel": [735, 465]}})
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_invalid_external_catalog_is_not_rewritten(self):
        changed = json.loads(self.path.read_text(encoding="utf-8"))
        changed["places"][1]["source_pixel"] = [False, 0]
        self.path.write_text(json.dumps(changed), encoding="utf-8")
        external = self.path.read_bytes()
        with self.assertRaises(ValueError):
            save_place_positions(self.path, self.coast, {"mondstadt": {"source_pixel": [735, 465]}})
        self.assertEqual(self.path.read_bytes(), external)
