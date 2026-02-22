"""Post-processing for layout results.

Snaps rectangle edges, resolves minor overlaps, and converts LayoutRect list
to Shapely Polygons for downstream geometry building.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from shapely.geometry import box, mapping

from topo2ifc.topology.model import LayoutRect

logger = logging.getLogger(__name__)


def snap_to_grid(rects: list[LayoutRect], grid: float = 0.05) -> list[LayoutRect]:
    """Round all coordinates to the nearest grid multiple."""
    out = []
    for r in rects:
        out.append(
            LayoutRect(
                space_id=r.space_id,
                x=round(round(r.x / grid) * grid, 6),
                y=round(round(r.y / grid) * grid, 6),
                width=max(grid, round(round(r.width / grid) * grid, 6)),
                height=max(grid, round(round(r.height / grid) * grid, 6)),
            )
        )
    return out


def check_overlaps(rects: list[LayoutRect], tol: float = 0.01) -> list[str]:
    """Return a list of overlap descriptions (empty = no overlaps)."""
    issues: list[str] = []
    polys = {r.space_id: box(r.x, r.y, r.x2, r.y2) for r in rects}
    ids = list(polys.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            inter = polys[a].intersection(polys[b])
            if inter.area > tol:
                issues.append(
                    f"Overlap between '{a}' and '{b}': area={inter.area:.3f} m²"
                )
    return issues


def to_shapely_polygons(rects: list[LayoutRect]) -> dict[str, "Polygon"]:
    """Convert LayoutRect list to a dict of Shapely Polygon objects."""
    from shapely.geometry import box as shapely_box

    return {r.space_id: shapely_box(r.x, r.y, r.x2, r.y2) for r in rects}


def save_layout_json(rects: list[LayoutRect], path: Path) -> None:
    """Save layout as JSON (space_id → {x, y, width, height})."""
    data = {r.space_id: r.to_dict() for r in rects}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Saved layout JSON → %s", path)


def save_layout_geojson(rects: list[LayoutRect], path: Path) -> None:
    """Save layout as GeoJSON FeatureCollection for visualisation."""
    features = []
    for r in rects:
        poly = box(r.x, r.y, r.x2, r.y2)
        features.append(
            {
                "type": "Feature",
                "properties": {"space_id": r.space_id, "area": round(r.area, 3)},
                "geometry": mapping(poly),
            }
        )
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Saved layout GeoJSON → %s", path)
