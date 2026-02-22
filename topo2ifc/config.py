"""Global configuration and defaults for topo2ifc."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GeometryConfig:
    """Default geometric parameters."""

    wall_height: float = 2.8
    wall_thickness: float = 0.15
    slab_thickness: float = 0.15
    door_width: float = 0.9
    door_height: float = 2.0
    storey_elevation: float = 0.0
    tolerance: float = 0.01


@dataclass
class SolverConfig:
    """Layout solver parameters."""

    solver: str = "heuristic"  # "heuristic" | "ortools"
    seed: int = 42
    solver_time_limit_sec: int = 60
    grid_unit: float = 0.5  # grid resolution for CP-SAT (metres)
    max_iter: int = 5000  # SA / hill-climbing iterations


@dataclass
class Config:
    """Top-level configuration."""

    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    debug_output_dir: Optional[Path] = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        geo_data = data.get("geometry", {})
        sol_data = data.get("solver", {})
        debug_dir = data.get("debug_output_dir")

        return cls(
            geometry=GeometryConfig(**geo_data) if geo_data else GeometryConfig(),
            solver=SolverConfig(**sol_data) if sol_data else SolverConfig(),
            debug_output_dir=Path(debug_dir) if debug_dir else None,
        )

    @classmethod
    def default(cls) -> "Config":
        return cls()
