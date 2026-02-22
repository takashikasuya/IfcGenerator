"""Constraint violation and objective-function reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_constraints_report(
    topology_errors: list[str],
    layout_errors: list[str],
    area_deviations: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build a serialisable report dict."""
    return {
        "topology_errors": topology_errors,
        "layout_errors": layout_errors,
        "area_deviations": area_deviations or {},
        "ok": len(topology_errors) == 0 and len(layout_errors) == 0,
    }


def save_constraints_report(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def compute_area_deviations(
    rects,  # list[LayoutRect]
    specs,  # list[SpaceSpec]
) -> dict[str, float]:
    """Return {space_id: area_deviation_m2} for each space."""
    spec_by_id = {s.space_id: s for s in specs}
    deviations: dict[str, float] = {}
    for rect in rects:
        spec = spec_by_id.get(rect.space_id)
        if spec is not None and spec.area_target is not None:
            deviations[rect.space_id] = round(rect.area - spec.area_target, 4)
    return deviations
