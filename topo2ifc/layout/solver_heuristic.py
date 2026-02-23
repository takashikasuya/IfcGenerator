"""Heuristic layout solver.

Strategy
--------
1. Order spaces in BFS order from the graph (corridor-first when possible).
2. Compute initial rectangle dimensions from area targets.
3. Place rectangles sequentially in a strip-packing style (left-to-right,
   new row when strip width exceeded).
4. Apply a simple hill-climbing swap loop to improve adjacency satisfaction.
"""

from __future__ import annotations

import logging
import math
import random
import re
from typing import Optional

from topo2ifc.config import SolverConfig
from topo2ifc.layout.solver_base import LayoutSolverBase
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect, SpaceCategory

logger = logging.getLogger(__name__)

# Maximum strip width used during initial placement (metres)
_DEFAULT_STRIP_WIDTH = 30.0


class HeuristicSolver(LayoutSolverBase):
    """Fast heuristic layout solver (no external solver dependency)."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        super().__init__(config)
        self._rng = random.Random(self.config.seed)

    def solve(self, topo: TopologyGraph) -> list[LayoutRect]:
        if len(topo) == 0:
            return []

        order = self._bfs_order(topo)
        order, preplaced = self._preplace_vertical_cores(topo, order)
        y_offset = max((r.y2 for r in preplaced), default=0.0)
        sparse_topology = not topo.adjacent_pairs() and not topo.connected_pairs()
        if sparse_topology:
            rects = self._compact_grid_placement(topo, order, y_offset=y_offset)
        else:
            rects = self._initial_placement(topo, order, y_offset=y_offset)
        rects = preplaced + rects
        # Preserve the vertical anchoring of preplaced cores (typically y=0)
        # even if the hill-climb optimizer swaps their positions.
        preplaced_heights = {id(r): (r.y2 - r.y1) for r in preplaced}
        rects = self._hill_climb(topo, rects)
        for r in preplaced:
            height = preplaced_heights.get(id(r))
            if height is not None:
                r.y1 = 0.0
                r.y2 = height
        return rects

    # ------------------------------------------------------------------ #
    # Step 1 – BFS ordering (corridor / entrance nodes first)
    # ------------------------------------------------------------------ #

    def _bfs_order(self, topo: TopologyGraph) -> list[str]:
        spaces = topo.spaces
        # prefer corridor or entrance as root
        root = None
        for sp in spaces:
            if sp.space_category in (SpaceCategory.CORRIDOR, SpaceCategory.ENTRANCE):
                root = sp.space_id
                break
        if root is None:
            root = spaces[0].space_id
        return topo.bfs_order(root)

    # ------------------------------------------------------------------ #
    # Step 1.5 – Reserve vertical circulation cores
    # ------------------------------------------------------------------ #

    def _preplace_vertical_cores(
        self,
        topo: TopologyGraph,
        order: list[str],
    ) -> tuple[list[str], list[LayoutRect]]:
        """Reserve stair/elevator core rectangles before room packing.

        Core candidates are detected from category/name/id hints and placed
        on the first row so all other spaces are packed above that reserved
        band. Core IDs with per-floor suffixes are normalized to keep a stable
        left-to-right ordering across storeys.
        """
        core_ids = [sid for sid in order if self._is_vertical_core(topo.get_space(sid))]
        if not core_ids:
            return order, []

        grid = self.config.grid_unit
        core_ids.sort(key=lambda sid: self._core_group_key(topo.get_space(sid)))

        preplaced: list[LayoutRect] = []
        x_cursor = 0.0
        for sid in core_ids:
            area = topo.get_space(sid).effective_area_target
            w, h = self._initial_dims(area)
            w = max(grid, round(w / grid) * grid)
            h = max(grid, round(h / grid) * grid)
            preplaced.append(LayoutRect(space_id=sid, x=round(x_cursor, 4), y=0.0, width=w, height=h))
            x_cursor += w

        remaining = [sid for sid in order if sid not in set(core_ids)]
        return remaining, preplaced

    @staticmethod
    def _is_vertical_core(spec) -> bool:
        category = (spec.category or "").strip().lower()
        text = f"{spec.space_id} {spec.name}".lower()
        return (
            category == SpaceCategory.CORE.value
            or "stair" in text
            or "elevator" in text
            or "lift" in text
        )

    @staticmethod
    def _core_group_key(spec) -> tuple[str, str]:
        text = f"{spec.space_id} {spec.name}".lower()
        base = re.sub(r"(_?f\d+|_?floor\d+)$", "", spec.space_id.lower())
        core_type = "stair" if "stair" in text else ("elevator" if ("elevator" in text or "lift" in text) else "core")
        return core_type, base

    # ------------------------------------------------------------------ #
    # Step 2 – Strip packing
    # ------------------------------------------------------------------ #

    def _initial_placement(
        self, topo: TopologyGraph, order: list[str], y_offset: float = 0.0
    ) -> list[LayoutRect]:
        rects: dict[str, LayoutRect] = {}
        dims: dict[str, tuple[float, float]] = {}
        total_area = 0.0
        max_w = 0.0
        grid = self.config.grid_unit

        for sid in order:
            spec = topo.get_space(sid)
            area = spec.effective_area_target
            w, h = self._initial_dims(area)
            w = max(grid, round(w / grid) * grid)
            h = max(grid, round(h / grid) * grid)
            dims[sid] = (w, h)
            total_area += w * h
            max_w = max(max_w, w)

        # Use total target area to derive a compact shelf width.
        # This prevents long one-directional strips when constraints are sparse.
        strip_width = max(max_w * 1.8, math.sqrt(total_area) * 1.35)
        strip_width = min(strip_width, _DEFAULT_STRIP_WIDTH)

        x_cursor = 0.0
        y_cursor = y_offset
        row_height = 0.0

        for sid in order:
            w, h = dims[sid]

            # new row if needed
            if x_cursor + w > strip_width and x_cursor > 0:
                y_cursor += row_height
                x_cursor = 0.0
                row_height = 0.0

            rects[sid] = LayoutRect(
                space_id=sid,
                x=round(x_cursor, 4),
                y=round(y_cursor, 4),
                width=w,
                height=h,
            )
            x_cursor += w
            row_height = max(row_height, h)

        return list(rects.values())

    def _compact_grid_placement(
        self, topo: TopologyGraph, order: list[str], y_offset: float = 0.0
    ) -> list[LayoutRect]:
        """Place sparse/disconnected spaces in a compact near-square grid."""
        if not order:
            return []

        grid = self.config.grid_unit
        dims: dict[str, tuple[float, float]] = {}
        for sid in order:
            area = topo.get_space(sid).effective_area_target
            w, h = self._initial_dims(area)
            w = max(grid, round(w / grid) * grid)
            h = max(grid, round(h / grid) * grid)
            dims[sid] = (w, h)

        n_cols = max(1, math.ceil(math.sqrt(len(order))))
        rows = [order[i:i + n_cols] for i in range(0, len(order), n_cols)]
        row_widths = [sum(dims[sid][0] for sid in row) for row in rows]
        row_heights = [max(dims[sid][1] for sid in row) for row in rows]
        max_row_w = max(row_widths) if row_widths else 0.0

        rects: list[LayoutRect] = []
        y_cursor = y_offset
        for row, row_w, row_h in zip(rows, row_widths, row_heights):
            x_cursor = (max_row_w - row_w) / 2.0
            for sid in row:
                w, h = dims[sid]
                rects.append(
                    LayoutRect(
                        space_id=sid,
                        x=round(x_cursor, 4),
                        y=round(y_cursor, 4),
                        width=w,
                        height=h,
                    )
                )
                x_cursor += w
            y_cursor += row_h
        return rects

    # ------------------------------------------------------------------ #
    # Step 3 – Hill climbing: swap positions to improve adjacency score
    # ------------------------------------------------------------------ #

    def _hill_climb(
        self, topo: TopologyGraph, rects: list[LayoutRect]
    ) -> list[LayoutRect]:
        adj_pairs = set(
            (min(a, b), max(a, b)) for a, b in topo.adjacent_pairs()
        )
        conn_pairs = set(
            (min(a, b), max(a, b)) for a, b in topo.connected_pairs()
        )
        desired = adj_pairs | conn_pairs

        if not desired:
            return rects

        rect_map = {r.space_id: r for r in rects}

        best_score = self._adjacency_score(rect_map, desired)

        for _ in range(self.config.max_iter):
            if len(rects) < 2:
                break
            i, j = self._rng.sample(range(len(rects)), 2)
            ri, rj = rects[i], rects[j]

            # swap positions
            ri_new = LayoutRect(ri.space_id, rj.x, rj.y, ri.width, ri.height)
            rj_new = LayoutRect(rj.space_id, ri.x, ri.y, rj.width, rj.height)
            rect_map[ri.space_id] = ri_new
            rect_map[rj.space_id] = rj_new

            score = self._adjacency_score(rect_map, desired)
            if score >= best_score and not _has_overlaps(list(rect_map.values())):
                rects[i] = ri_new
                rects[j] = rj_new
                best_score = score
            else:
                # revert
                rect_map[ri.space_id] = ri
                rect_map[rj.space_id] = rj

        logger.debug("Hill-climbing final adjacency score: %.3f", best_score)
        return rects

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #

    @staticmethod
    def _adjacency_score(
        rect_map: dict[str, LayoutRect],
        desired: set[tuple[str, str]],
    ) -> float:
        """Score = fraction of desired adjacencies that are physically touching."""
        if not desired:
            return 1.0

        satisfied = 0
        for a, b in desired:
            ra = rect_map.get(a)
            rb = rect_map.get(b)
            if ra is None or rb is None:
                continue
            if _rects_touch(ra, rb):
                satisfied += 1

        return satisfied / len(desired)


# --------------------------------------------------------------------------- #
# Geometry helper
# --------------------------------------------------------------------------- #


def _rects_touch(a: LayoutRect, b: LayoutRect, tol: float = 0.1) -> bool:
    """Return True when two rectangles share an edge (or near-miss within tol)."""
    x_gap = max(a.x, b.x) - min(a.x2, b.x2)
    y_gap = max(a.y, b.y) - min(a.y2, b.y2)
    # touching on x-axis, overlapping on y (vertical shared edge)
    x_touch = abs(x_gap) <= tol
    y_overlap = min(a.y2, b.y2) - max(a.y, b.y) > tol
    # touching on y-axis, overlapping on x (horizontal shared edge)
    y_touch = abs(y_gap) <= tol
    x_overlap = min(a.x2, b.x2) - max(a.x, b.x) > tol

    return (x_touch and y_overlap) or (y_touch and x_overlap)


def _has_overlaps(rects: list[LayoutRect], tol: float = 0.01) -> bool:
    """Return True if any two rectangles overlap by more than tol."""
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            inter_w = min(a.x2, b.x2) - max(a.x, b.x)
            inter_h = min(a.y2, b.y2) - max(a.y, b.y)
            if inter_w > tol and inter_h > tol:
                return True
    return False
