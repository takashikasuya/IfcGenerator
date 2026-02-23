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
        y_offset = max((r.height for r in preplaced), default=0.0)
        sparse_topology = not topo.adjacent_pairs() and not topo.connected_pairs()
        if sparse_topology:
            rects = self._compact_grid_placement(topo, order, y_offset=y_offset)
        else:
            rects = self._initial_placement(topo, order, y_offset=y_offset)
        rects = preplaced + rects
        # Preserve the vertical anchoring of preplaced cores (typically y=0)
        # even if the hill-climb optimizer swaps their positions.
        preplaced_heights = {id(r): r.height for r in preplaced}
        rects = self._hill_climb(topo, rects)
        for r in preplaced:
            height = preplaced_heights.get(id(r))
            if height is not None:
                r.y = 0.0
                r.height = height
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
        core_specs = [topo.get_space(sid) for sid in core_ids]
        core_ids.sort(key=lambda sid: self._core_group_key(topo.get_space(sid)))

        split_core_mode = self._is_split_core_layout(core_specs)
        left_group: list[str] = []
        right_group: list[str] = []
        if split_core_mode:
            left_group, right_group = self._split_core_groups(core_ids)
            ordered_groups = left_group + right_group
        else:
            ordered_groups = core_ids

        preplaced: list[LayoutRect] = []
        x_cursor = 0.0
        core_dims: dict[str, tuple[float, float]] = {}
        for sid in ordered_groups:
            area = topo.get_space(sid).effective_area_target
            w, h = self._initial_dims(area)
            w = max(grid, round(w / grid) * grid)
            h = max(grid, round(h / grid) * grid)
            core_dims[sid] = (w, h)

        if split_core_mode and left_group and right_group:
            left_width = sum(core_dims[sid][0] for sid in left_group)
            right_width = sum(core_dims[sid][0] for sid in right_group)
            gap = max(2.0 * grid, 0.5 * (left_width + right_width))

            for sid in left_group:
                w, h = core_dims[sid]
                preplaced.append(LayoutRect(space_id=sid, x=round(x_cursor, 4), y=0.0, width=w, height=h))
                x_cursor += w

            x_cursor += gap

            for sid in right_group:
                w, h = core_dims[sid]
                preplaced.append(LayoutRect(space_id=sid, x=round(x_cursor, 4), y=0.0, width=w, height=h))
                x_cursor += w
        else:
            for sid in ordered_groups:
                w, h = core_dims[sid]
                preplaced.append(LayoutRect(space_id=sid, x=round(x_cursor, 4), y=0.0, width=w, height=h))
                x_cursor += w

        if split_core_mode:
            preplaced.sort(key=lambda r: r.x)

        for rect in preplaced:
            # normalize tiny negative zeros from rounding
            if abs(rect.x) < 1e-9:
                rect.x = 0.0

        core_id_set = set(core_ids)
        remaining = [sid for sid in order if sid not in core_id_set]
        return remaining, preplaced

    def _is_split_core_layout(self, core_specs: list) -> bool:
        labels = [self._core_side_label(spec) for spec in core_specs]
        # Only consider explicitly side-labeled cores ("left"/"right") when
        # determining if this is a split-core layout; ignore "center" cores.
        side_labels = [label for label in labels if label in ("left", "right")]
        if len(side_labels) < 2:
            return False
        # Treat as split-core only if we have cores on both sides.
        return len(set(side_labels)) >= 2

    def _split_core_groups(self, cores: list) -> tuple[list, list]:
        """
        Group cores into left/right buckets using the same side-label logic as
        `_is_split_core_layout`. The input may be either spec-like objects
        (with `space_id` and `name` attributes) or plain identifiers.
        """
        def _side_label_for_core(core) -> str:
            # Prefer full spec-based labeling when attributes are available,
            # fall back to ID-only labeling for backwards compatibility.
            if hasattr(core, "space_id") and hasattr(core, "name"):
                return self._core_side_label(core)
            return self._core_side_label_from_id(str(core))

        left_group = [core for core in cores if _side_label_for_core(core) == "left"]
        right_group = [core for core in cores if _side_label_for_core(core) == "right"]

        unlabeled = [core for core in cores if core not in left_group and core not in right_group]
        for core in unlabeled:
            if len(left_group) <= len(right_group):
                left_group.append(core)
            else:
                right_group.append(core)
        return left_group, right_group

    def _core_side_label(self, spec) -> str:
        return self._core_side_label_from_id(f"{spec.space_id} {spec.name}")

    @staticmethod
    def _core_side_label_from_id(text: str) -> str:
        lowered = text.lower()
        if any(tok in lowered for tok in ("west", "left", "core_a", "a_core", "north")):
            return "left"
        if any(tok in lowered for tok in ("east", "right", "core_b", "b_core", "south")):
            return "right"
        return "center"

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

        best_score = self._combined_score(topo, rect_map, desired)

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

            score = self._combined_score(topo, rect_map, desired)
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

    def _combined_score(
        self,
        topo: TopologyGraph,
        rect_map: dict[str, LayoutRect],
        desired: set[tuple[str, str]],
    ) -> float:
        """Return weighted score that includes adjacency and circulation quality."""
        adjacency = self._adjacency_score(rect_map, desired)
        circulation = self._circulation_score(topo, rect_map)
        return adjacency + 0.2 * circulation

    def _circulation_score(
        self,
        topo: TopologyGraph,
        rect_map: dict[str, LayoutRect],
    ) -> float:
        """Score stair/elevator placement quality.

        - Stairs: reward proximity to corridor spaces and penalize dead-end neighbors.
        - Elevators: reward central placement based on weighted travel distance.
        """
        if not rect_map:
            return 0.0

        spaces = {s.space_id: s for s in topo.spaces}
        stair_ids = [sid for sid in rect_map if sid in spaces and self._core_type(spaces[sid]) == "stair"]
        elevator_ids = [sid for sid in rect_map if sid in spaces and self._core_type(spaces[sid]) == "elevator"]
        corridor_ids = [
            sid for sid in rect_map if sid in spaces and spaces[sid].space_category == SpaceCategory.CORRIDOR
        ]

        score = 0.0
        if stair_ids:
            score += self._stair_score(topo, rect_map, spaces, stair_ids, corridor_ids)
        if elevator_ids:
            score += self._elevator_score(rect_map, spaces, elevator_ids)
        return score

    def _stair_score(
        self,
        topo: TopologyGraph,
        rect_map: dict[str, LayoutRect],
        spaces,
        stair_ids: list[str],
        corridor_ids: list[str],
    ) -> float:
        score = 0.0
        for stair_id in stair_ids:
            stair_rect = rect_map[stair_id]
            if corridor_ids:
                nearest_corridor = min(
                    self._rect_distance(stair_rect, rect_map[cid]) for cid in corridor_ids
                )
                score += 1.0 / (1.0 + nearest_corridor)

            dead_end_neighbors = 0
            for nid in topo.neighbors(stair_id):
                neighbor = spaces.get(nid)
                if neighbor is None:
                    continue
                is_dead_end = sum(1 for _ in topo.neighbors(nid)) <= 1
                is_corridor = neighbor.space_category == SpaceCategory.CORRIDOR
                is_core = self._is_vertical_core(neighbor)
                if is_dead_end and not is_corridor and not is_core:
                    dead_end_neighbors += 1

            score -= 0.25 * dead_end_neighbors
        return score

    def _elevator_score(
        self,
        rect_map: dict[str, LayoutRect],
        spaces,
        elevator_ids: list[str],
    ) -> float:
        candidates = [
            sid
            for sid, spec in spaces.items()
            if sid in rect_map and not self._is_vertical_core(spec)
        ]
        if not candidates:
            return 0.0

        total_weight = 0.0
        weighted_distance = 0.0
        for sid in candidates:
            target = rect_map[sid]
            weight = max(1.0, spaces[sid].effective_area_target)
            dist = min(
                self._rect_distance(target, rect_map[eid])
                for eid in elevator_ids
            )
            weighted_distance += weight * dist
            total_weight += weight

        if total_weight <= 0.0:
            return 0.0

        avg_distance = weighted_distance / total_weight
        return 1.0 / (1.0 + avg_distance)

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

    @staticmethod
    def _core_type(spec) -> str:
        text = f"{spec.space_id} {spec.name}".lower()
        if "stair" in text:
            return "stair"
        if "elevator" in text or "lift" in text:
            return "elevator"
        return "core"

    @staticmethod
    def _rect_distance(a: LayoutRect, b: LayoutRect) -> float:
        return math.hypot(a.cx - b.cx, a.cy - b.cy)


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
