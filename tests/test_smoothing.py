import copy
import json
import math
import unittest
from pathlib import Path

from coastline_style import intersection_pairs, smooth_coastline, smooth_ring


def distance_to_ring(point, ring):
    distances = []
    for a, b in zip(ring, ring[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = dx*dx+dy*dy
        t = max(0, min(1, ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0
        distances.append(math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy))
    return min(distances)


class SmoothingTests(unittest.TestCase):
    def test_movement_is_bounded_and_ring_remains_closed(self):
        raw = [(0,0),(10,0),(10,10),(6,10),(6,4),(4,4),(4,10),(0,10),(0,0)]
        smooth = smooth_ring(raw)
        self.assertEqual(smooth[0], smooth[-1])
        self.assertNotEqual(smooth, raw)
        for point in smooth:
            self.assertLessEqual(distance_to_ring(point, raw), .4500001)
        for a, b in zip(raw, raw[1:]):
            for step in range(10):
                t = step/10
                p = (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)
                self.assertLessEqual(distance_to_ring(p, smooth), .4500001)
        self.assertFalse(intersection_pairs([smooth]))

    def test_tiny_islands_are_unchanged(self):
        tiny = [(0,0),(2,0),(2,2),(0,2),(0,0)]
        self.assertEqual(smooth_ring(tiny), tiny)

    def test_shipped_coast_has_no_new_intersections_or_lost_islands(self):
        data = json.loads((Path(__file__).resolve().parents[1] / "data/coastline.json").read_text())
        original = copy.deepcopy(data["polygons"])
        unit = data["km_per_source_pixel"]
        smooth = smooth_coastline(original, unit)
        self.assertEqual(original, data["polygons"])
        self.assertEqual(len(smooth), len(original))
        in_pixels = [[(x/unit,y/unit) for x,y in ring] for ring in smooth]
        self.assertFalse(intersection_pairs(in_pixels))
        # Check the corrected inlet and its island after smoothing, too.
        from test_user_coastline import contains
        x1,y1,x2,y2 = data["source_bounds_px"]
        for x,y,expected in [(730,455,False),(729,459,False),(731,465,True),(606,108,True)]:
            point = ((x-(x1+x2)/2)*unit,(y-(y1+y2)/2)*unit)
            self.assertEqual(any(contains(point,r) for r in smooth), expected)
