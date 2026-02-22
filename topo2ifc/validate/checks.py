"""Validation checks for topology and layout."""

from __future__ import annotations

from topo2ifc.layout.postprocess import check_overlaps
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect, SpaceSpec


def validate_topology(topo: TopologyGraph) -> list[str]:
    """Return a list of topology-level validation errors."""
    errors: list[str] = []
    errors.extend(topo.validate())

    # Check that connected pairs reference valid spaces
    space_ids = {s.space_id for s in topo.spaces}
    for a, b in topo.connected_pairs():
        if a not in space_ids:
            errors.append(f"Connection references unknown space: {a}")
        if b not in space_ids:
            errors.append(f"Connection references unknown space: {b}")

    return errors


def validate_layout(
    rects: list[LayoutRect],
    specs: list[SpaceSpec],
    tol: float = 0.01,
) -> list[str]:
    """Return a list of layout-level validation errors."""
    errors: list[str] = []

    spec_by_id = {s.space_id: s for s in specs}

    # Check overlaps
    errors.extend(check_overlaps(rects, tol=tol))

    # Check all spaces have a rectangle
    rect_ids = {r.space_id for r in rects}
    for spec in specs:
        if spec.space_id not in rect_ids:
            errors.append(f"Space '{spec.space_id}' has no layout rectangle.")

    # Check area constraints
    for rect in rects:
        spec = spec_by_id.get(rect.space_id)
        if spec is None:
            continue
        if spec.area_min is not None and rect.area < spec.area_min - tol:
            errors.append(
                f"Space '{rect.space_id}' area {rect.area:.2f} m² < min {spec.area_min:.2f} m²."
            )

    return errors
