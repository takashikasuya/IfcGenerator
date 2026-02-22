"""Abstract base class for Layout Solvers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from topo2ifc.config import SolverConfig
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect


class LayoutSolverBase(ABC):
    """All layout solvers must implement :meth:`solve`."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        self.config = config or SolverConfig()

    @abstractmethod
    def solve(self, topo: TopologyGraph) -> list[LayoutRect]:
        """Return a rectangle for each space in *topo*.

        Raises
        ------
        RuntimeError
            If no feasible layout can be found.
        """

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _initial_dims(area_target: float, aspect_ratio: float = 1.5) -> tuple[float, float]:
        """Compute initial width/height from area and aspect ratio."""
        import math

        w = math.sqrt(area_target * aspect_ratio)
        h = area_target / w
        return round(w, 2), round(h, 2)
