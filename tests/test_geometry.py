import math
import unittest

from geometry import (KM_PER_DEGREE, RADIUS_KM, Viewport, distance_km,
                      great_circle, to_latlon)


class GeometryTests(unittest.TestCase):
    def test_planet_convention(self):
        self.assertAlmostEqual(2 * math.pi * RADIUS_KM, 40_000)
        self.assertAlmostEqual(distance_km((-10_000, 0), (10_000, 0)), 20_000)
        self.assertAlmostEqual(distance_km((0, -10_000), (0, 10_000)), 20_000)

    def test_equator_and_meridian_quarter(self):
        self.assertAlmostEqual(distance_km((0, 0), (10_000, 0)), 10_000)
        self.assertAlmostEqual(distance_km((0, 0), (0, 10_000)), 10_000)

    def test_wrap_shorter_than_flat_map(self):
        self.assertAlmostEqual(distance_km((-9900, 0), (29900, 0)), 200)

    def test_latitude_changes_distance(self):
        equator = distance_km((0, 0), (1000, 0))
        northern = distance_km((0, -60 * KM_PER_DEGREE), (1000, -60 * KM_PER_DEGREE))
        self.assertTrue(490 < northern < 510)
        self.assertGreater(equator, northern)

    def test_coincident_and_poles(self):
        self.assertEqual(distance_km((0, 0), (0, 0)), 0)
        self.assertLess(distance_km((-9000, -10_000), (29_000, -10_000)), 1e-10)

    def test_great_circle_represents_measured_distance(self):
        a, b = (-7000, -6000), (9000, 5000)
        paths = great_circle(a, b)
        length = sum(distance_km(p, q) for path in paths for p, q in zip(path, path[1:]))
        self.assertAlmostEqual(length, distance_km(a, b), places=6)

    def test_routes_handle_antipodes_and_seam(self):
        for a, b in [((0, 0), (20_000, 0)), ((0, 0), (0, 0)),
                     ((-9900, -1000), (29_900, -1000))]:
            paths = great_circle(a, b)
            self.assertTrue(all(math.isfinite(c) for path in paths for p in path for c in p))
            self.assertTrue(all(abs(p[0] - q[0]) < 20_000 for path in paths
                                for p, q in zip(path, path[1:])))

    def test_projection_roundtrip_at_named_point(self):
        self.assertEqual(to_latlon(10_000, -5000), (45, 90))
        self.assertEqual(to_latlon(30_000, 0), (0, -90))

    def test_zoom_preserves_mouse_anchor_and_pan_roundtrip(self):
        v = Viewport(1000, 700)
        v.fit((-10_000, -10_000, 10_000, 10_000))
        before = v.world(237, 189)
        for _ in range(20):
            v.zoom(237, 189, 1.25)
        for got, expected in zip(v.world(237, 189), before):
            self.assertAlmostEqual(got, expected)
        old = (v.cx, v.cy)
        v.pan(32, -78)
        v.pan(-32, 78)
        for got, expected in zip((v.cx, v.cy), old):
            self.assertAlmostEqual(got, expected)
        self.assertGreater(v.scale, 0)


if __name__ == "__main__":
    unittest.main()
