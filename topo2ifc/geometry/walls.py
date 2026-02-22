"""Wall segment extraction from 2-D space polygons.

For each space, we extract the exterior edges and classify them as either
*exterior walls* (not shared with any other space) or *partition walls*
(shared boundary with an adjacent space).

A WallSegment is the unit that the IFC exporter turns into an IfcWall.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from shapely.geometry import LineString, Polygon

from topo2ifc.geometry.geom2d import exterior_edges, shared_boundary


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


def extract_walls(
    polygons: dict[str, Polygon],
    wall_thickness: float = 0.15,
    wall_height: float = 2.8,
    tol: float = 0.05,
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
    space_ids = list(polygons.keys())
    segments: list[WallSegment] = []
    processed_partitions: set[frozenset] = set()

    for sid, poly in polygons.items():
        for edge in exterior_edges(poly):
            if edge.length < tol:
                continue

            # Check if this edge is shared with any other space
            shared_partner: Optional[str] = None
            for other_id, other_poly in polygons.items():
                if other_id == sid:
                    continue
                inter = edge.buffer(tol).intersection(other_poly.boundary)
                if not inter.is_empty and inter.length > tol:
                    shared_partner = other_id
                    break

            if shared_partner is not None:
                # Partition wall – emit once
                key = frozenset([sid, shared_partner])
                if key in processed_partitions:
                    continue
                processed_partitions.add(key)
                coords = list(edge.coords)
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
                        shared_with=shared_partner,
                    )
                )
            else:
                # Exterior wall
                coords = list(edge.coords)
                segments.append(
                    WallSegment(
                        x1=coords[0][0],
                        y1=coords[0][1],
                        x2=coords[-1][0],
                        y2=coords[-1][1],
                        thickness=wall_thickness,
                        height=wall_height,
                        is_exterior=True,
                        space_id=sid,
                    )
                )

    return segments
