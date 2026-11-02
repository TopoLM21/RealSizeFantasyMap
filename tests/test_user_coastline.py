"""Checks on the shipped coastline artifacts, without optional image packages."""

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def contains(point, ring):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


class UserCoastlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((DATA / "coastline.json").read_text(encoding="utf-8"))

    def source_is_land(self, x, y):
        x1, y1, x2, y2 = self.data["source_bounds_px"]
        unit = self.data["km_per_source_pixel"]
        point = ((x - (x1 + x2) / 2) * unit, (y - (y1 + y2) / 2) * unit)
        return any(contains(point, ring) for ring in self.data["polygons"])

    def test_land_is_retained_but_decoration_and_ocean_are_not(self):
        for point in [(520, 160), (550, 420), (500, 650), (803, 793)]:
            with self.subTest(land=point):
                self.assertTrue(self.source_is_land(*point))
        for point in [(850, 167), (40, 500), (512, 805), (200, 200), (599, 459)]:
            with self.subTest(water=point):
                self.assertFalse(self.source_is_land(*point))

    def test_closed_rings_and_normalized_scale(self):
        for ring in self.data["polygons"]:
            self.assertGreaterEqual(len(ring), 4)
            self.assertEqual(ring[0], ring[-1])
        self.assertAlmostEqual(self.data["km_per_source_pixel"], 20_000 / 776)
        self.assertTrue(self.data["source_sha256"].startswith("de6eac28"))

    def test_svg_and_geojson_represent_the_same_land(self):
        svg = ET.parse(DATA / "coastline.svg")
        paths = svg.findall(".//{http://www.w3.org/2000/svg}path")
        geojson = json.loads((DATA / "coastline.geojson").read_text(encoding="utf-8"))
        self.assertEqual(len(paths), len(self.data["polygons"]))
        self.assertEqual(len(geojson["features"]), len(paths))
        for feature, ring in zip(geojson["features"], self.data["polygons"]):
            exported = feature["geometry"]["coordinates"][0]
            self.assertEqual(exported[0], exported[-1])
            expected = {(round(x * .009, 7), round(-y * .009, 7)) for x, y in ring}
            self.assertEqual({tuple(p) for p in exported}, expected)

    def test_legacy_coastline_remains_available(self):
        legacy = json.loads((DATA / "coastline-v4.json").read_text(encoding="utf-8"))
        self.assertEqual(legacy["title"], "Тейват · снимок 4.0")
        self.assertNotEqual(legacy["polygons"], self.data["polygons"])


if __name__ == "__main__":
    unittest.main()
