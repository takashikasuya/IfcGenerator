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
from topo2ifc.topology.model import AdjacencyEdge, ConnectionEdge, LayoutRect, SpaceCategory, SpaceSpec

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

        storey_rects = self._solve_storey_groups(topo)
        if storey_rects is not None:
            return storey_rects

        order = self._bfs_order(topo)
        sparse_topology = not topo.adjacent_pairs() and not topo.connected_pairs()
        if sparse_topology:
            rects = self._compact_grid_placement(topo, order)
        else:
            rects = self._initial_placement(topo, order)
        rects = self._hill_climb(topo, rects)
        return rects

    def _solve_storey_groups(self, topo: TopologyGraph) -> Optional[list[LayoutRect]]:
        """Solve each storey independently and stack them vertically.

        Core spaces keep a deterministic X slot across storeys so stair/elevator
        shafts can remain aligned in plan.
        """
        storey_groups: dict[float, list[str]] = {}
        for spec in topo.spaces:
            elev = round(spec.storey_elevation or 0.0, 4)
            storey_groups.setdefault(elev, []).append(spec.space_id)

        if len(storey_groups) <= 1:
            return None

        all_adj = topo.adjacent_pairs()
        all_conn = topo.connected_pairs()

        y_offset = 0.0
        floor_gap = self.config.grid_unit * 4
        core_x_slots: dict[str, float] = {}
        stacked_rects: list[LayoutRect] = []

        for elev in sorted(storey_groups.keys()):
            ids = set(storey_groups[elev])
            spaces = [topo.get_space(sid) for sid in storey_groups[elev]]
            adj = [
                (a, b)
                for a, b in all_adj
                if a in ids and b in ids
            ]
            conn = [
                (a, b)
                for a, b in all_conn
                if a in ids and b in ids
            ]
            floor_topo = TopologyGraph.from_parts(
                spaces=spaces,
                adjacencies=[],
                connections=[],
            )
            for a, b in adj:
                floor_topo.add_adjacency(AdjacencyEdge(space_a=a, space_b=b))
            for a, b in conn:
                floor_topo.add_connection(
                    ConnectionEdge(
                        space_a=a,
                        space_b=b,
                        door_width=None,
                        door_height=None,
                    )
                )

            floor_order = self._bfs_order(floor_topo)
            sparse_topology = not floor_topo.adjacent_pairs() and not floor_topo.connected_pairs()
            if sparse_topology:
                floor_rects = self._compact_grid_placement(
                    floor_topo, floor_order, core_x_slots=core_x_slots
                )
            else:
                floor_rects = self._initial_placement(
                    floor_topo, floor_order, core_x_slots=core_x_slots
                )
            floor_rects = self._hill_climb(floor_topo, floor_rects)

            min_y = min(r.y for r in floor_rects)
            max_y = max(r.y2 for r in floor_rects)
            height = max_y - min_y
            for rect in floor_rects:
                stacked_rects.append(
                    LayoutRect(
                        space_id=rect.space_id,
                        x=rect.x,
                        y=rect.y - min_y + y_offset,
                        width=rect.width,
                        height=rect.height,
                    )
                )
            y_offset += height + floor_gap

        return stacked_rects

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
    # Step 2 – Strip packing
    # ------------------------------------------------------------------ #

    def _initial_placement(
        self,
        topo: TopologyGraph,
        order: list[str],
        core_x_slots: Optional[dict[str, float]] = None,
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

        core_ids = self._vertical_core_ids(topo, order)
        core_set = set(core_ids)
        x_cursor = 0.0
        y_cursor = 0.0
        row_height = 0.0

        for sid in core_ids:
            w, h = dims[sid]
            slot_key = self._core_alignment_key(topo.get_space(sid))
            if core_x_slots is not None and slot_key:
                x_val = core_x_slots.setdefault(slot_key, x_cursor)
            else:
                x_val = x_cursor
            rects[sid] = LayoutRect(
                space_id=sid,
                x=round(x_val, 4),
                y=0.0,
                width=w,
                height=h,
            )
            x_cursor = max(x_cursor, x_val + w)
            row_height = max(row_height, h)

        if core_ids:
            y_cursor = row_height + grid
            x_cursor = 0.0
            row_height = 0.0

        for sid in order:
            if sid in core_set:
                continue
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
        self,
        topo: TopologyGraph,
        order: list[str],
        core_x_slots: Optional[dict[str, float]] = None,
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

        core_ids = self._vertical_core_ids(topo, order)
        core_set = set(core_ids)
        non_core = [sid for sid in order if sid not in core_set]

        n_cols = max(1, math.ceil(math.sqrt(len(non_core) or 1)))
        rows = [non_core[i:i + n_cols] for i in range(0, len(non_core), n_cols)]
        row_widths = [sum(dims[sid][0] for sid in row) for row in rows]
        row_heights = [max(dims[sid][1] for sid in row) for row in rows]
        max_row_w = max(row_widths) if row_widths else 0.0

        rects: list[LayoutRect] = []

        x_cursor = 0.0
        core_h = 0.0
        for sid in core_ids:
            w, h = dims[sid]
            slot_key = self._core_alignment_key(topo.get_space(sid))
            if core_x_slots is not None and slot_key:
                x_val = core_x_slots.setdefault(slot_key, x_cursor)
            else:
                x_val = x_cursor
            rects.append(
                LayoutRect(
                    space_id=sid,
                    x=round(x_val, 4),
                    y=0.0,
                    width=w,
                    height=h,
                )
            )
            x_cursor = max(x_cursor, x_val + w)
            core_h = max(core_h, h)

        y_cursor = core_h + (grid if core_ids else 0.0)
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

    def _vertical_core_ids(self, topo: TopologyGraph, order: list[str]) -> list[str]:
        """Return IDs reserved as vertical cores, ordered by core-placement score."""
        core_ids: list[str] = []
        for sid in order:
            spec = topo.get_space(sid)
            token = f"{spec.category} {spec.name}".lower()
            if spec.space_category == SpaceCategory.CORE or "stair" in token or "elevator" in token:
                core_ids.append(sid)

        def _score(sid: str) -> tuple[int, float, str]:
            spec = topo.get_space(sid)
            token = f"{spec.category} {spec.name}".lower()
            if "stair" in token:
                return (0, self._stair_adjacency_score(topo, sid), sid)
            if "elevator" in token:
                return (1, self._elevator_centrality_score(topo, sid), sid)
            return (2, float(topo.degree(sid)), sid)

        return [sid for sid, _ in sorted(((sid, _score(sid)) for sid in core_ids), key=lambda x: (x[1][0], -x[1][1], x[1][2]))]

    def _stair_adjacency_score(self, topo: TopologyGraph, sid: str) -> float:
        """Higher is better: near corridors and away from dead-end placement."""
        neighbors = list(topo.neighbors(sid))
        if not neighbors:
            return -10.0

        corridor_links = 0
        for nid in neighbors:
            n_spec = topo.get_space(nid)
            if n_spec.space_category == SpaceCategory.CORRIDOR:
                corridor_links += 1

        degree = topo.degree(sid)
        dead_end_penalty = 2.0 if degree <= 1 else 0.0
        return corridor_links * 3.0 + degree - dead_end_penalty

    def _elevator_centrality_score(self, topo: TopologyGraph, sid: str) -> float:
        """Higher is better: minimize weighted shortest-path distance to spaces."""
        total_weight = 0.0
        weighted_distance = 0.0
        for oid in topo.space_ids():
            if oid == sid:
                continue
            spec = topo.get_space(oid)
            weight = max(1.0, spec.effective_area_target)
            dist = topo.shortest_path_length(sid, oid)
            if dist is None:
                dist = 100
            total_weight += weight
            weighted_distance += weight * dist

        if total_weight <= 0:
            return -1e6
        # Negate distance so "higher is better" in sorting.
        return -(weighted_distance / total_weight)

    @staticmethod
    def _core_alignment_key(spec: SpaceSpec) -> str:
        """Build a stable key for aligning same-type cores across storeys."""
        source = f"{spec.category} {spec.name}".lower()
        if "stair" in source:
            base = "stair"
        elif "elevator" in source:
            base = "elevator"
        else:
            base = spec.space_id.lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
        return normalized or spec.space_id.lower()

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
