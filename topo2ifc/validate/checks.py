"""Validation checks for topology and layout."""

from __future__ import annotations

from topo2ifc.layout.postprocess import check_overlaps
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect, SpaceSpec, VerticalCoreSpec


def validate_topology(
    topo: TopologyGraph,
    vertical_cores: list[VerticalCoreSpec] | None = None,
    storey_count: int | None = None,
    highrise_elevator_threshold: int = 6,
) -> list[str]:
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

    resolved_storey_count = storey_count
    if resolved_storey_count is None:
        storey_ids = {s.storey_id for s in topo.spaces if s.storey_id}
        if len(storey_ids) > 0:
            resolved_storey_count = len(storey_ids)
        else:
            elevations = {s.storey_elevation for s in topo.spaces if s.storey_elevation is not None}
            resolved_storey_count = max(1, len(elevations))

    core_specs = vertical_cores or []
    core_types = {c.core_type.lower() for c in core_specs}

    if resolved_storey_count >= 2 and "stair" not in core_types:
        errors.append(
            "Multi-storey topology requires at least one stair core (storey_count >= 2)."
        )

    if (
        resolved_storey_count >= highrise_elevator_threshold
        and "elevator" not in core_types
    ):
        errors.append(
            "High-rise topology requires at least one elevator core "
            f"(storey_count >= {highrise_elevator_threshold})."
        )

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


def validate_shaft_openings(
    openings_by_elevation: dict[float, LayoutRect],
) -> list[str]:
    """Validate generated shaft openings before IFC export."""
    errors: list[str] = []
    if not openings_by_elevation:
        return errors

    for elev, rect in openings_by_elevation.items():
        if rect.width <= 0 or rect.height <= 0:
            errors.append(f"Shaft opening at elevation {elev:.3f} has non-positive dimensions.")

    if len(openings_by_elevation) >= 2:
        first = next(iter(openings_by_elevation.values()))
        for elev, rect in openings_by_elevation.items():
            if abs(rect.width - first.width) > 1e-6 or abs(rect.height - first.height) > 1e-6:
                errors.append(
                    f"Shaft opening size mismatch at elevation {elev:.3f}: "
                    f"expected {first.width:.3f}x{first.height:.3f}, got {rect.width:.3f}x{rect.height:.3f}."
                )
    return errors
