"""OR-Tools CP-SAT based layout solver.

Each space is modelled as a rectangle (x, y, w, h) on an integer grid.
The solver enforces:
  * No-overlap between rectangles
  * Area bounds  (w * h >= min_area_grid, close to target_area_grid)
  * Adjacency soft-constraints (rewarded when rects touch)

OR-Tools is an optional dependency.  If it is not installed this module raises
``ImportError`` at import time and the CLI falls back to the heuristic solver.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from topo2ifc.config import SolverConfig
from topo2ifc.layout.solver_base import LayoutSolverBase
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect

logger = logging.getLogger(__name__)

try:
    from ortools.sat.python import cp_model  # type: ignore
except ImportError as _err:
    raise ImportError(
        "ortools is required for the CP-SAT solver. "
        "Install it with: pip install ortools"
    ) from _err


class OrtoolsSolver(LayoutSolverBase):
    """Rectangle-packing layout solver using OR-Tools CP-SAT."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        super().__init__(config)

    def solve(self, topo: TopologyGraph) -> list[LayoutRect]:
        spaces = topo.spaces
        if not spaces:
            return []

        grid = self.config.grid_unit  # metres per grid unit
        min_areas_g = [max(1, math.ceil(sp.effective_area_min / (grid * grid))) for sp in spaces]
        target_areas_g = [max(1, round(sp.effective_area_target / (grid * grid))) for sp in spaces]
        total_target = sum(target_areas_g)

        max_area_g = max(target_areas_g) * 4
        max_dim_g = max(8, int(math.sqrt(total_target) * 3.0))
        max_coord_g = max_dim_g * 3

        model = cp_model.CpModel()

        xs, ys, ws, hs, xes, yes = [], [], [], [], [], []
        x_intervals, y_intervals = [], []
        area_vars = []
        center_x2, center_y2 = [], []

        for i, sp in enumerate(spaces):
            x = model.new_int_var(0, max_coord_g, f"x_{i}")
            y = model.new_int_var(0, max_coord_g, f"y_{i}")
            w = model.new_int_var(1, max_dim_g, f"w_{i}")
            h = model.new_int_var(1, max_dim_g, f"h_{i}")
            xe = model.new_int_var(0, max_coord_g + max_dim_g, f"xe_{i}")
            ye = model.new_int_var(0, max_coord_g + max_dim_g, f"ye_{i}")
            model.add(xe == x + w)
            model.add(ye == y + h)

            xs.append(x)
            ys.append(y)
            ws.append(w)
            hs.append(h)
            xes.append(xe)
            yes.append(ye)

            x_intervals.append(model.new_interval_var(x, w, xe, f"xi_{i}"))
            y_intervals.append(model.new_interval_var(y, h, ye, f"yi_{i}"))

            area = model.new_int_var(min_areas_g[i], max_area_g, f"area_{i}")
            model.AddMultiplicationEquality(area, [w, h])
            area_vars.append(area)
            model.add(area >= min_areas_g[i])

            cx2 = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"cx2_{i}")
            cy2 = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"cy2_{i}")
            model.add(cx2 == 2 * x + w)
            model.add(cy2 == 2 * y + h)
            center_x2.append(cx2)
            center_y2.append(cy2)

        # No-overlap constraint
        model.add_no_overlap_2d(x_intervals, y_intervals)

        # Objective term 1: area accuracy
        deviations = []
        for i in range(len(spaces)):
            dev = model.new_int_var(0, max_area_g, f"dev_{i}")
            model.add_abs_equality(dev, area_vars[i] - target_areas_g[i])
            deviations.append(dev)

        # Objective term 2: compactness (bounding rectangle)
        max_x = model.new_int_var(0, max_coord_g + max_dim_g, "bbox_max_x")
        max_y = model.new_int_var(0, max_coord_g + max_dim_g, "bbox_max_y")
        model.add_max_equality(max_x, xes)
        model.add_max_equality(max_y, yes)

        # Objective term 3: keep desired adjacency/connection pairs close.
        space_index = {sp.space_id: i for i, sp in enumerate(spaces)}
        desired_pairs = set((min(a, b), max(a, b)) for a, b in (topo.adjacent_pairs() + topo.connected_pairs()))
        pair_dist_vars = []
        for a, b in desired_pairs:
            ia = space_index.get(a)
            ib = space_index.get(b)
            if ia is None or ib is None:
                continue
            dx = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"pair_dx_{ia}_{ib}")
            dy = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"pair_dy_{ia}_{ib}")
            model.add_abs_equality(dx, center_x2[ia] - center_x2[ib])
            model.add_abs_equality(dy, center_y2[ia] - center_y2[ib])
            pair_dist_vars.append(dx)
            pair_dist_vars.append(dy)

        # Objective term 4: discourage same-type core clustering for split-core fallbacks.
        core_conflict_penalties = []
        for ia, ib in self._core_conflict_pairs(spaces):
            dx = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"core_dx_{ia}_{ib}")
            dy = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"core_dy_{ia}_{ib}")
            model.add_abs_equality(dx, center_x2[ia] - center_x2[ib])
            model.add_abs_equality(dy, center_y2[ia] - center_y2[ib])
            manhattan = model.new_int_var(0, 4 * (max_coord_g + max_dim_g), f"core_dist_{ia}_{ib}")
            model.add(manhattan == dx + dy)
            proximity = model.new_int_var(0, 2 * max_dim_g, f"core_proximity_{ia}_{ib}")
            model.add_max_equality(proximity, [0, (2 * max_dim_g) - manhattan])
            core_conflict_penalties.append(proximity)

        # Objective term 5: keep corresponding vertical cores stacked in XY.
        # Enabled only for multi-storey mode to preserve single-storey behavior.
        core_stack_dist_vars = []
        if self.config.multi_storey_mode:
            for ia, ib in self._core_stack_pairs(spaces):
                dx = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"stack_dx_{ia}_{ib}")
                dy = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"stack_dy_{ia}_{ib}")
                model.add_abs_equality(dx, center_x2[ia] - center_x2[ib])
                model.add_abs_equality(dy, center_y2[ia] - center_y2[ib])
                core_stack_dist_vars.append(dx)
                core_stack_dist_vars.append(dy)

        # Objective term 6: vertical circulation efficiency proxy.
        # Penalize horizontal distance from non-core spaces to nearest stair/elevator.
        circulation_penalties = []
        if self.config.multi_storey_mode:
            stair_ids = [i for i, sp in enumerate(spaces) if self._core_type(sp) == "stair"]
            elevator_ids = [i for i, sp in enumerate(spaces) if self._core_type(sp) == "elevator"]
            non_core_ids = [i for i, sp in enumerate(spaces) if self._core_type(sp) not in {"stair", "elevator"}]

            for i in non_core_ids:
                if stair_ids:
                    stair_dist = []
                    for j in stair_ids:
                        dx = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"stair_dx_{i}_{j}")
                        dy = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"stair_dy_{i}_{j}")
                        manhattan = model.new_int_var(0, 4 * (max_coord_g + max_dim_g), f"stair_dist_{i}_{j}")
                        model.add_abs_equality(dx, center_x2[i] - center_x2[j])
                        model.add_abs_equality(dy, center_y2[i] - center_y2[j])
                        model.add(manhattan == dx + dy)
                        stair_dist.append(manhattan)
                    nearest_stair = model.new_int_var(0, 4 * (max_coord_g + max_dim_g), f"nearest_stair_{i}")
                    model.add_min_equality(nearest_stair, stair_dist)
                    circulation_penalties.append(nearest_stair)

                if elevator_ids:
                    elev_dist = []
                    for j in elevator_ids:
                        dx = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"elev_dx_{i}_{j}")
                        dy = model.new_int_var(0, 2 * (max_coord_g + max_dim_g), f"elev_dy_{i}_{j}")
                        manhattan = model.new_int_var(0, 4 * (max_coord_g + max_dim_g), f"elev_dist_{i}_{j}")
                        model.add_abs_equality(dx, center_x2[i] - center_x2[j])
                        model.add_abs_equality(dy, center_y2[i] - center_y2[j])
                        model.add(manhattan == dx + dy)
                        elev_dist.append(manhattan)
                    nearest_elev = model.new_int_var(0, 4 * (max_coord_g + max_dim_g), f"nearest_elev_{i}")
                    model.add_min_equality(nearest_elev, elev_dist)
                    circulation_penalties.append(nearest_elev)

        model.minimize(
            100 * sum(deviations)
            + 10 * (max_x + max_y)
            + sum(pair_dist_vars)
            + 5 * sum(core_conflict_penalties)
            + 5 * sum(core_stack_dist_vars)
            + sum(circulation_penalties)
        )

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.solver_time_limit_sec
        solver.parameters.random_seed = self.config.seed
        solver.parameters.log_search_progress = False

        status = solver.solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                f"CP-SAT solver returned status {solver.status_name(status)}. "
                "Consider relaxing constraints or using the heuristic solver."
            )

        results: list[LayoutRect] = []
        for i, sp in enumerate(spaces):
            x_val = solver.value(xs[i]) * grid
            y_val = solver.value(ys[i]) * grid
            w_val = solver.value(ws[i]) * grid
            h_val = solver.value(hs[i]) * grid
            results.append(
                LayoutRect(
                    space_id=sp.space_id,
                    x=round(x_val, 4),
                    y=round(y_val, 4),
                    width=round(w_val, 4),
                    height=round(h_val, 4),
                )
            )

        return results

    def _core_conflict_pairs(self, spaces) -> list[tuple[int, int]]:
        typed: list[tuple[int, str]] = []
        for i, sp in enumerate(spaces):
            ctype = self._core_type(sp)
            if ctype in {"stair", "elevator"}:
                typed.append((i, ctype))

        pairs: list[tuple[int, int]] = []
        for i in range(len(typed)):
            for j in range(i + 1, len(typed)):
                if typed[i][1] == typed[j][1]:
                    pairs.append((typed[i][0], typed[j][0]))
        return pairs

    @staticmethod
    def _core_type(spec) -> str:
        text = f"{spec.space_id} {spec.name}".lower()
        if "stair" in text:
            return "stair"
        if "elevator" in text or "lift" in text:
            return "elevator"
        return "other"

    def _core_stack_pairs(self, spaces) -> list[tuple[int, int]]:
        grouped: dict[tuple[str, str], list[int]] = {}
        for i, sp in enumerate(spaces):
            ctype = self._core_type(sp)
            if ctype not in {"stair", "elevator"}:
                continue
            key = (ctype, self._core_stack_base(sp))
            grouped.setdefault(key, []).append(i)

        pairs: list[tuple[int, int]] = []
        for ids in grouped.values():
            if len(ids) < 2:
                continue
            ids_sorted = sorted(ids)
            for i in range(len(ids_sorted) - 1):
                pairs.append((ids_sorted[i], ids_sorted[i + 1]))
        return pairs

    @staticmethod
    def _core_stack_base(spec) -> str:
        sid = str(spec.space_id).lower()
        for tok in ("_f", "-f", "_l", "-l", "_level", "-level"):
            idx = sid.find(tok)
            if idx > 0:
                return sid[:idx]
        return sid
