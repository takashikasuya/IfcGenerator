"""2-D geometry utilities built on Shapely.

Provides helpers for extracting wall segments from space polygons and
computing shared boundaries between adjacent spaces.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import unary_union


def shared_boundary(poly_a: Polygon, poly_b: Polygon, tol: float = 0.01) -> Optional[LineString]:
    """Return the shared edge between two adjacent polygons, or None."""
    inter = poly_a.buffer(tol).intersection(poly_b.buffer(tol))
    if inter.is_empty:
        return None
    # Extract linear geometry from intersection
    boundary = inter.boundary
    if boundary.is_empty:
        return None
    if isinstance(boundary, (LineString, MultiLineString)):
        return boundary if not boundary.is_empty else None
    # For polygon intersections use the boundary
    return boundary if isinstance(boundary, LineString) else None


def exterior_edges(polygon: Polygon) -> list[LineString]:
    """Return the exterior edges of a polygon as a list of LineStrings."""
    coords = list(polygon.exterior.coords)
    edges = []
    for i in range(len(coords) - 1):
        edges.append(LineString([coords[i], coords[i + 1]]))
    return edges


def midpoint(line: LineString) -> Point:
    """Return the midpoint of a LineString."""
    return line.interpolate(0.5, normalized=True)


def door_position(shared: LineString, door_width: float = 0.9) -> Optional[tuple[float, float]]:
    """Return the centre XY of a door opening on the shared boundary."""
    length = shared.length
    if length < door_width:
        return None
    mid = midpoint(shared)
    return (mid.x, mid.y)


def polygon_area(polygon: Polygon) -> float:
    return polygon.area


def is_valid_layout(polygons: dict[str, Polygon], tol: float = 0.01) -> tuple[bool, list[str]]:
    """Check that all polygons are valid and non-overlapping."""
    errors: list[str] = []
    ids = list(polygons.keys())
    for sid, poly in polygons.items():
        if not poly.is_valid:
            errors.append(f"Space '{sid}' has an invalid polygon: {poly.explain_validity()}")

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            inter = polygons[a].intersection(polygons[b])
            if inter.area > tol:
                errors.append(f"Overlap between '{a}' and '{b}': {inter.area:.3f} m²")

    return len(errors) == 0, errors


def offset_polygon(polygon: Polygon, distance: float) -> Polygon:
    """Inset (negative distance) or outset a polygon."""
    result = polygon.buffer(-distance)
    if isinstance(result, MultiPolygon):
        # Return the largest part
        return max(result.geoms, key=lambda g: g.area)
    return result
