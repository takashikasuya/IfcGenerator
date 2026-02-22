"""Wall segment extraction from 2-D space polygons.

v0.2:
- Exterior walls are derived from the union envelope of all space polygons.
- Partition walls are derived from pairwise shared boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from topo2ifc.geometry.geom2d import shared_boundary


@dataclass
class WallSegment:
    """A single straight wall segment in the 2-D floor plan."""

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    height: float
    is_exterior: bool
    space_id: Optional[str] = None  # owning space (exterior) or None (partition)
    shared_with: Optional[str] = None  # neighbouring space id for partition walls
    elevation: float = 0.0

    @property
    def length(self) -> float:
        return float(np.linalg.norm([self.x2 - self.x1, self.y2 - self.y1]))

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def direction(self) -> tuple[float, float]:
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        length = self.length
        return (dx / length, dy / length) if length > 1e-9 else (1.0, 0.0)


def _iter_lines(geom) -> Iterable[LineString]:
    """Yield LineString parts from a Shapely geometry."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        for g in geom.geoms:
            if isinstance(g, LineString) and not g.is_empty:
                yield g
    elif isinstance(geom, Polygon):
        coords = list(geom.exterior.coords)
        for i in range(len(coords) - 1):
            yield LineString([coords[i], coords[i + 1]])
    elif isinstance(geom, MultiPolygon):
        for g in geom.geoms:
            yield from _iter_lines(g)
    elif isinstance(geom, GeometryCollection):
        for g in geom.geoms:
            yield from _iter_lines(g)


def extract_walls(
    polygons: dict[str, Polygon],
    wall_thickness: float = 0.15,
    wall_height: float = 2.8,
    tol: float = 0.05,
    space_elevations: Optional[dict[str, float]] = None,
) -> list[WallSegment]:
    """Extract wall segments from all space polygons.

    Parameters
    ----------
    polygons:
        Mapping of space_id → Shapely Polygon.
    wall_thickness:
        Default wall thickness in metres.
    wall_height:
        Wall height in metres.
    tol:
        Tolerance for shared-boundary detection.

    Returns
    -------
    list[WallSegment]
        Deduplicated wall segments.
    """
    segments: list[WallSegment] = []
    processed_partitions: set[tuple[str, str, tuple[tuple[float, float], tuple[float, float]]]] = set()
    space_elevations = space_elevations or {}
    if not polygons:
        return []

    # ------------------------------------------------------------------ #
    # 1) Exterior walls from full building envelope
    # ------------------------------------------------------------------ #
    merged = unary_union(list(polygons.values()))
    boundary = merged.boundary
    default_elev = min(space_elevations.values()) if space_elevations else 0.0
    for line in _iter_lines(boundary):
        if line.length < tol:
            continue
        coords = list(line.coords)
        segments.append(
            WallSegment(
                x1=coords[0][0],
                y1=coords[0][1],
                x2=coords[-1][0],
                y2=coords[-1][1],
                thickness=wall_thickness,
                height=wall_height,
                is_exterior=True,
                elevation=default_elev,
            )
        )

    # ------------------------------------------------------------------ #
    # 2) Partition walls from shared boundaries
    # ------------------------------------------------------------------ #
    ids = list(polygons.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sid = ids[i]
            oid = ids[j]
            sb = shared_boundary(polygons[sid], polygons[oid], tol=tol)
            for line in _iter_lines(sb):
                if line.length < tol:
                    continue
                coords = list(line.coords)
                p1 = (round(coords[0][0], 6), round(coords[0][1], 6))
                p2 = (round(coords[-1][0], 6), round(coords[-1][1], 6))
                key = (sid, oid, tuple(sorted([p1, p2])))
                if key in processed_partitions:
                    continue
                processed_partitions.add(key)
                segments.append(
                    WallSegment(
                        x1=coords[0][0],
                        y1=coords[0][1],
                        x2=coords[-1][0],
                        y2=coords[-1][1],
                        thickness=wall_thickness,
                        height=wall_height,
                        is_exterior=False,
                        space_id=sid,
                        shared_with=oid,
                        elevation=min(
                            space_elevations.get(sid, 0.0),
                            space_elevations.get(oid, 0.0),
                        ),
                    )
                )

    return segments
