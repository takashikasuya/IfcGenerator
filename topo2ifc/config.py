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
    highrise_elevator_threshold: int = 6
    multi_storey_mode: bool = False


@dataclass
class ElementThermalConfig:
    """Material and thermal metadata for an exported IFC element type."""

    material_name: str
    thermal_conductivity: float
    density: float
    specific_heat_capacity: float


@dataclass
class MaterialThermalConfig:
    """Material/thermal defaults used for IFC element enrichment."""

    wall: ElementThermalConfig = field(
        default_factory=lambda: ElementThermalConfig(
            material_name="GenericWall",
            thermal_conductivity=0.72,
            density=1800.0,
            specific_heat_capacity=840.0,
        )
    )
    slab: ElementThermalConfig = field(
        default_factory=lambda: ElementThermalConfig(
            material_name="GenericSlab",
            thermal_conductivity=1.40,
            density=2300.0,
            specific_heat_capacity=880.0,
        )
    )
    door: ElementThermalConfig = field(
        default_factory=lambda: ElementThermalConfig(
            material_name="GenericDoor",
            thermal_conductivity=0.14,
            density=650.0,
            specific_heat_capacity=1600.0,
        )
    )


@dataclass
class Config:
    """Top-level configuration."""

    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    material_thermal: MaterialThermalConfig = field(default_factory=MaterialThermalConfig)
    debug_output_dir: Optional[Path] = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        geo_data = data.get("geometry", {})
        sol_data = data.get("solver", {})
        material_thermal_data = data.get("material_thermal", {})
        debug_dir = data.get("debug_output_dir")

        def _element_cfg(key: str, defaults: ElementThermalConfig) -> ElementThermalConfig:
            section = material_thermal_data.get(key, {})
            return ElementThermalConfig(**section) if section else defaults

        material_thermal = MaterialThermalConfig(
            wall=_element_cfg("wall", MaterialThermalConfig().wall),
            slab=_element_cfg("slab", MaterialThermalConfig().slab),
            door=_element_cfg("door", MaterialThermalConfig().door),
        )

        return cls(
            geometry=GeometryConfig(**geo_data) if geo_data else GeometryConfig(),
            solver=SolverConfig(**sol_data) if sol_data else SolverConfig(),
            material_thermal=material_thermal,
            debug_output_dir=Path(debug_dir) if debug_dir else None,
        )

    @classmethod
    def default(cls) -> "Config":
        return cls()
