"""Slab (floor) geometry utilities.

v0.1: One IfcSlab per space (or one for the entire storey).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shapely.geometry import Polygon
from shapely.ops import unary_union


@dataclass
class SlabSpec:
    """Specification for a single floor slab."""

    space_id: str  # owning space (or "__floor__" for storey-wide slab)
    polygon: Polygon
    elevation: float = 0.0
    thickness: float = 0.15


def extract_slabs(
    polygons: dict[str, Polygon],
    elevation: float = 0.0,
    slab_thickness: float = 0.15,
    space_elevations: Optional[dict[str, float]] = None,
) -> list[SlabSpec]:
    """Return merged storey slabs (one slab per elevation group)."""
    space_elevations = space_elevations or {}
    grouped: dict[float, list[Polygon]] = {}
    for sid, poly in polygons.items():
        elev = round(space_elevations.get(sid, elevation), 3)
        grouped.setdefault(elev, []).append(poly)

    slabs: list[SlabSpec] = []
    for elev, polys in grouped.items():
        merged = unary_union(polys)
        if isinstance(merged, Polygon):
            slab_poly = merged
        else:
            # Keep a single polygon for v0.1 exporter by using envelope.
            slab_poly = merged.envelope
        slabs.append(
            SlabSpec(
                space_id=f"__floor__{elev:.3f}",
                polygon=slab_poly,
                elevation=elev,
                thickness=slab_thickness,
            )
        )
    return slabs


def merge_slabs(slabs: list[SlabSpec]) -> SlabSpec | None:
    """Merge all per-space slabs into a single storey slab."""
    if not slabs:
        return None
    from shapely.ops import unary_union

    merged = unary_union([s.polygon for s in slabs])
    elevation = slabs[0].elevation
    thickness = slabs[0].thickness
    return SlabSpec(
        space_id="__floor__",
        polygon=merged,
        elevation=elevation,
        thickness=thickness,
    )
