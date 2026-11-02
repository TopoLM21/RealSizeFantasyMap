"""Preparation-tool checks; optional image packages are not needed to run the atlas."""

import importlib.util
import unittest

HAS_TOOLS = all(importlib.util.find_spec(name) is not None for name in ("PIL", "numpy", "scipy"))


@unittest.skipUnless(HAS_TOOLS, "Optional image preparation packages are not installed")
class LineArtTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw
        from tools.vectorize_user_map import segment
        self.source = Image.new("RGB", (80, 60), "white")
        self.draw = ImageDraw.Draw(self.source)
        self.segment = segment
        self.profile = {"mode": "line_art", "image_size": [80, 60], "crop": [0, 0, 80, 60],
                        "ink_threshold": 200, "minimum_land_area_px": 4,
                        "closing_radius_px": 0, "water_cuts": []}

    def test_closed_land_is_filled_but_open_strokes_are_not(self):
        self.draw.rectangle((10, 10, 30, 40), outline="black", width=2)
        self.draw.line([(50, 10), (65, 10), (65, 40)], fill="black", width=2)
        mask = self.segment(self.source, self.profile)
        self.assertTrue(mask[25, 20])
        self.assertFalse(mask[25, 60])
        self.assertFalse(mask[10, 55])
        self.assertFalse(mask[0, 0])

    def test_shared_ink_boundary_does_not_merge_land_regions(self):
        from scipy import ndimage as ndi
        from tools.vectorize_user_map import trace_rings
        self.draw.rectangle((10, 10, 30, 40), outline="black", width=2)
        self.draw.rectangle((30, 10, 50, 40), outline="black", width=2)
        mask = self.segment(self.source, self.profile)
        self.assertTrue(mask[25, 20])
        self.assertTrue(mask[25, 40])
        self.assertFalse(mask[25, 30])
        self.assertEqual(ndi.label(mask)[1], 2)
        self.assertEqual(len(trace_rings(mask, tolerance=0.45)), 2)

    def test_small_island_enclosed_by_gray_ink_survives(self):
        self.draw.rectangle((20, 20, 24, 24), outline=(170, 170, 170), width=1)
        mask = self.segment(self.source, self.profile)
        self.assertTrue(mask[22, 22])
        self.assertEqual(int(mask.sum()), 9)


if __name__ == "__main__":
    unittest.main()
