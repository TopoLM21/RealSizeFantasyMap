"""Bounded visual smoothing. Original coordinates and distances stay unchanged."""

import math
from collections import defaultdict


def _area(points):
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:]))) / 2


def _resample(ring, step):
    points = []
    for a, b in zip(ring, ring[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-12:
            continue
        count = max(1, math.ceil(length / step))
        for i in range(count):
            t = i / count
            points.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return points


def smooth_ring(ring, max_deviation=0.45, step=0.8, iterations=3):
    """Low-pass a closed ring, in source pixels, with a pointwise movement cap.

    Corresponding line segments remain within max_deviation of the original
    segments in both directions. Tiny islands retain their original geometry.
    """
    original = [tuple(p) for p in ring]
    if len(original) < 4 or _area(original) < 16 or max_deviation <= 0:
        return original
    baseline = _resample(original, step)
    if len(baseline) < 3:
        return original
    points = baseline[:]
    for _ in range(iterations):
        updated = []
        for i, center in enumerate(points):
            before, after = points[i - 1], points[(i + 1) % len(points)]
            x = .25 * before[0] + .5 * center[0] + .25 * after[0]
            y = .25 * before[1] + .5 * center[1] + .25 * after[1]
            bx, by = baseline[i]
            dx, dy = x - bx, y - by
            distance = math.hypot(dx, dy)
            if distance > max_deviation:
                factor = max_deviation / distance
                x, y = bx + dx * factor, by + dy * factor
            updated.append((x, y))
        points = updated
    candidate = points + [points[0]]
    if _area(candidate) < .9 * _area(original):
        return original
    return candidate


def _intersects(a, b, c, d):
    eps = 1e-9
    if (max(a[0], b[0]) + eps < min(c[0], d[0]) or
            max(c[0], d[0]) + eps < min(a[0], b[0]) or
            max(a[1], b[1]) + eps < min(c[1], d[1]) or
            max(c[1], d[1]) + eps < min(a[1], b[1])):
        return False

    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    ab1, ab2, cd1, cd2 = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((ab1 <= eps and ab2 >= -eps or ab2 <= eps and ab1 >= -eps) and
            (cd1 <= eps and cd2 >= -eps or cd2 <= eps and cd1 >= -eps))


def intersection_pairs(rings, cell_size=2):
    """Find intersecting ring pairs, including nonadjacent self intersections."""
    grid = defaultdict(list)
    pairs = set()
    for ri, ring in enumerate(rings):
        segment_count = len(ring) - 1
        for si, (a, b) in enumerate(zip(ring, ring[1:])):
            cells = [(x, y)
                     for x in range(math.floor(min(a[0], b[0]) / cell_size),
                                    math.floor(max(a[0], b[0]) / cell_size) + 1)
                     for y in range(math.floor(min(a[1], b[1]) / cell_size),
                                    math.floor(max(a[1], b[1]) / cell_size) + 1)]
            seen = set()
            for cell in cells:
                for rj, sj, c, d in grid[cell]:
                    if (rj, sj) in seen:
                        continue
                    seen.add((rj, sj))
                    if ri == rj and (abs(si - sj) <= 1 or {si, sj} == {0, segment_count - 1}):
                        continue
                    pair = (rj, ri)
                    if pair not in pairs and _intersects(a, b, c, d):
                        pairs.add(pair)
            entry = (ri, si, a, b)
            for cell in cells:
                grid[cell].append(entry)
    return pairs


def smooth_coastline(polygons, km_per_pixel):
    """Smooth in pixel units; fall back where smoothing adds an intersection."""
    raw = [[(x / km_per_pixel, y / km_per_pixel) for x, y in ring] for ring in polygons]
    result = [smooth_ring(ring) for ring in raw]
    existing = intersection_pairs(raw)
    reverted = set()
    for _ in range(len(raw) + 1):
        new_conflicts = intersection_pairs(result) - existing
        if not new_conflicts:
            break
        changed = False
        for pair in new_conflicts:
            for index in pair:
                if index not in reverted:
                    result[index] = raw[index]
                    reverted.add(index)
                    changed = True
        if not changed:
            return [list(map(tuple, ring)) for ring in polygons]
    return [[(x * km_per_pixel, y * km_per_pixel) for x, y in ring] for ring in result]
