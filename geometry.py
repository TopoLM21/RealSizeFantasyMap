"""Spherical distances and an equidistant cylindrical drawing projection.

All map coordinates are kilometres at the equator, not screen pixels.
The planet's circumference is exactly 40,000 km by the prototype's convention.
"""

import math

CIRCUMFERENCE_KM = 40_000.0
RADIUS_KM = CIRCUMFERENCE_KM / (2 * math.pi)
KM_PER_DEGREE = CIRCUMFERENCE_KM / 360
WORLD_BOUNDS = (-10_000.0, -10_000.0, 30_000.0, 10_000.0)


def to_latlon(x, y):
    return -y / KM_PER_DEGREE, ((x / KM_PER_DEGREE + 180) % 360) - 180


def distance_km(a, b):
    """Shortest surface distance; stable at identical and antipodal points."""
    lat1, lon1 = map(math.radians, to_latlon(*a))
    lat2, lon2 = map(math.radians, to_latlon(*b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def great_circle(a, b, steps=100):
    """Return the measured great circle, split at the map's longitude seam.

    Antipodes have infinitely many shortest paths. Pick a deterministic plane.
    """
    def vector(point):
        lat, lon = map(math.radians, to_latlon(*point))
        return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))

    u, v = vector(a), vector(b)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(u, v))))
    angle = math.acos(dot)
    tangent = tuple(v[i] - dot * u[i] for i in range(3))
    length = math.sqrt(sum(c * c for c in tangent))
    if length < 1e-10:
        if dot > 0:
            return [[a, b]]
        axis = min(range(3), key=lambda i: abs(u[i]))
        tangent = tuple((1.0 if i == axis else 0.0) - u[axis] * u[i] for i in range(3))
        length = math.sqrt(sum(c * c for c in tangent))
    tangent = tuple(c / length for c in tangent)
    paths = [[]]
    for step in range(steps + 1):
        t = angle * step / steps
        p = tuple(math.cos(t) * u[i] + math.sin(t) * tangent[i] for i in range(3))
        lon = math.degrees(math.atan2(p[1], p[0]))
        lat = math.degrees(math.atan2(p[2], math.hypot(p[0], p[1])))
        x = ((lon + 90) % 360 - 90) * KM_PER_DEGREE
        point = (x, -lat * KM_PER_DEGREE)
        if paths[-1] and abs(point[0] - paths[-1][-1][0]) > 20_000:
            paths.append([])
        paths[-1].append(point)
    return paths


class Viewport:
    def __init__(self, width=900, height=800):
        self.width, self.height = width, height
        self.cx = self.cy = 0.0
        self.scale = 0.03

    def screen(self, x, y):
        return ((x - self.cx) * self.scale + self.width / 2,
                (y - self.cy) * self.scale + self.height / 2)

    def world(self, sx, sy):
        return ((sx - self.width / 2) / self.scale + self.cx,
                (sy - self.height / 2) / self.scale + self.cy)

    def fit(self, bounds):
        x1, y1, x2, y2 = bounds
        self.cx, self.cy = (x1 + x2) / 2, (y1 + y2) / 2
        self.scale = min(self.width / (x2 - x1), self.height / (y2 - y1)) * 0.88

    def zoom(self, sx, sy, factor):
        anchor = self.world(sx, sy)
        minimum = min(self.width / 40_000, self.height / 20_000) * 0.5
        self.scale = max(minimum, min(minimum * 256, self.scale * factor))
        after = self.world(sx, sy)
        self.cx += anchor[0] - after[0]
        self.cy += anchor[1] - after[1]

    def pan(self, dx, dy):
        self.cx -= dx / self.scale
        self.cy -= dy / self.scale
