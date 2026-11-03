import json
import unittest
from pathlib import Path

from places import load_places, search_places

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
        self.assertTrue(unplaced)
        self.assertTrue(all(p["x"] is None and p["y"] is None for p in unplaced))
        self.assertTrue(all(p["source"].startswith("https://wiki.hoyolab.com/") for p in unplaced))

    def test_place_projection_agrees_with_existing_example(self):
        point = next(p for p in self.places if p["id"] == "mondstadt")
        example = next(p for p in self.coast["demo_markers"] if "Мондштадт" in p[0])
        self.assertAlmostEqual(point["x"], example[1], places=3)
        self.assertAlmostEqual(point["y"], example[2], places=3)
