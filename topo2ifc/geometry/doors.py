"""Door placement on shared boundaries.

For each connectedTo edge, we find the shared boundary between the two space
polygons and place a door at its midpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shapely.geometry import LineString, Polygon

from topo2ifc.geometry.geom2d import door_position, shared_boundary


@dataclass
class DoorSpec:
    """A door instance between two spaces."""

    space_a: str
    space_b: str
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0  # rotation in degrees (0 = opening along X-axis)
    elevation: float = 0.0


def extract_doors(
    polygons: dict[str, Polygon],
    connected_pairs: list[tuple[str, str]],
    door_width: float = 0.9,
    door_height: float = 2.0,
    tol: float = 0.05,
    space_elevations: Optional[dict[str, float]] = None,
) -> list[DoorSpec]:
    """Return a :class:`DoorSpec` for each connectedTo pair.

    Parameters
    ----------
    polygons:
        space_id → Shapely Polygon
    connected_pairs:
        List of (space_a, space_b) tuples from topology connections.
    door_width, door_height:
        Default door dimensions.
    tol:
        Tolerance for boundary detection.
    """
    doors: list[DoorSpec] = []
    space_elevations = space_elevations or {}

    for a, b in connected_pairs:
        poly_a = polygons.get(a)
        poly_b = polygons.get(b)
        if poly_a is None or poly_b is None:
            continue

        pos = _find_door_position(poly_a, poly_b, door_width, tol)
        if pos is None:
            continue

        cx, cy, angle = pos
        doors.append(
            DoorSpec(
                space_a=a,
                space_b=b,
                x=cx,
                y=cy,
                width=door_width,
                height=door_height,
                angle=angle,
                elevation=min(
                    space_elevations.get(a, 0.0),
                    space_elevations.get(b, 0.0),
                ),
            )
        )

    return doors


def _find_door_position(
    poly_a: Polygon,
    poly_b: Polygon,
    door_width: float,
    tol: float,
) -> Optional[tuple[float, float, float]]:
    """Return (cx, cy, angle_deg) for the door, or None if no shared boundary."""
    inter = poly_a.buffer(tol).boundary.intersection(poly_b.buffer(tol).boundary)
    if inter.is_empty:
        return None

    # Use the longest intersection segment
    if hasattr(inter, "geoms"):
        segments = list(inter.geoms)
        segment = max(segments, key=lambda s: getattr(s, "length", 0))
    else:
        segment = inter

    if not hasattr(segment, "length") or segment.length < door_width:
        return None

    mid = segment.interpolate(0.5, normalized=True)

    # Compute angle from segment direction
    coords = list(segment.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    import math
    angle = math.degrees(math.atan2(dy, dx))

    return (mid.x, mid.y, angle)
