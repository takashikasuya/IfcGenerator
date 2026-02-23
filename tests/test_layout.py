"""Tests for the layout solver and post-processing."""

import pytest

from topo2ifc.config import SolverConfig
from topo2ifc.layout.postprocess import check_overlaps, snap_to_grid, to_shapely_polygons
from topo2ifc.layout.solver_heuristic import HeuristicSolver, _rects_touch
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import (
    AdjacencyEdge,
    ConnectionEdge,
    LayoutRect,
    SpaceSpec,
)


def _make_topo() -> TopologyGraph:
    """Small 4-space topology (3 rooms + corridor)."""
    spaces = [
        SpaceSpec("corridor", name="Corridor", category="corridor", area_target=15.0, area_min=10.0),
        SpaceSpec("room_a", name="Room A", category="meeting", area_target=20.0, area_min=15.0),
        SpaceSpec("room_b", name="Room B", category="office", area_target=25.0, area_min=18.0),
        SpaceSpec("room_c", name="Room C", category="toilet", area_target=8.0, area_min=5.0),
    ]
    adjacencies = [
        AdjacencyEdge("room_a", "corridor"),
        AdjacencyEdge("room_b", "corridor"),
        AdjacencyEdge("room_c", "corridor"),
    ]
    connections = [
        ConnectionEdge("room_a", "corridor"),
        ConnectionEdge("room_b", "corridor"),
    ]
    return TopologyGraph.from_parts(spaces, adjacencies, connections)


class TestHeuristicSolver:
    def test_returns_rect_per_space(self):
        topo = _make_topo()
        solver = HeuristicSolver(SolverConfig(seed=42))
        rects = solver.solve(topo)
        assert len(rects) == len(topo.spaces)

    def test_all_spaces_present(self):
        topo = _make_topo()
        solver = HeuristicSolver(SolverConfig(seed=42))
        rects = solver.solve(topo)
        ids = {r.space_id for r in rects}
        assert ids == {s.space_id for s in topo.spaces}

    def test_no_overlaps(self):
        topo = _make_topo()
        solver = HeuristicSolver(SolverConfig(seed=42))
        rects = solver.solve(topo)
        rects = snap_to_grid(rects)
        overlaps = check_overlaps(rects)
        assert overlaps == [], f"Unexpected overlaps: {overlaps}"

    def test_areas_positive(self):
        topo = _make_topo()
        solver = HeuristicSolver(SolverConfig(seed=42))
        rects = solver.solve(topo)
        for r in rects:
            assert r.area > 0

    def test_empty_topology(self):
        topo = TopologyGraph()
        solver = HeuristicSolver()
        rects = solver.solve(topo)
        assert rects == []

    def test_single_space(self):
        topo = TopologyGraph()
        topo.add_space(SpaceSpec("s1", area_target=20.0))
        solver = HeuristicSolver(SolverConfig(seed=0))
        rects = solver.solve(topo)
        assert len(rects) == 1
        assert rects[0].area > 0

    def test_disconnected_spaces_all_placed(self):
        topo = TopologyGraph()
        topo.add_space(SpaceSpec("s1", area_target=20.0))
        topo.add_space(SpaceSpec("s2", area_target=18.0))
        topo.add_space(SpaceSpec("s3", area_target=16.0))
        solver = HeuristicSolver(SolverConfig(seed=0))
        rects = solver.solve(topo)
        assert len(rects) == 3
        assert {r.space_id for r in rects} == {"s1", "s2", "s3"}

    def test_disconnected_layout_is_reasonably_compact(self):
        topo = TopologyGraph()
        for i in range(7):
            topo.add_space(SpaceSpec(f"s{i+1}", area_target=20.0))
        solver = HeuristicSolver(SolverConfig(seed=0))
        rects = solver.solve(topo)
        min_x = min(r.x for r in rects)
        min_y = min(r.y for r in rects)
        max_x = max(r.x2 for r in rects)
        max_y = max(r.y2 for r in rects)
        total_w = max_x - min_x
        total_h = max_y - min_y
        aspect = max(total_w, total_h) / max(1e-9, min(total_w, total_h))
        assert aspect <= 2.2

    def test_preplaces_vertical_cores_before_other_spaces(self):
        topo = TopologyGraph()
        topo.add_space(SpaceSpec("stair_f1", name="Main Stair", category="core", area_target=9.0))
        topo.add_space(SpaceSpec("elevator_f1", name="Main Elevator", category="core", area_target=6.0))
        topo.add_space(SpaceSpec("room_a", category="office", area_target=20.0))
        topo.add_space(SpaceSpec("room_b", category="meeting", area_target=16.0))

        solver = HeuristicSolver(SolverConfig(seed=42, grid_unit=0.5))
        rects = solver.solve(topo)
        rect_map = {r.space_id: r for r in rects}

        core_band_height = max(rect_map["stair_f1"].height, rect_map["elevator_f1"].height)
        assert rect_map["stair_f1"].y == pytest.approx(0.0)
        assert rect_map["elevator_f1"].y == pytest.approx(0.0)
        assert rect_map["room_a"].y >= core_band_height - 1e-9
        assert rect_map["room_b"].y >= core_band_height - 1e-9


class TestOrtoolsSolver:
    def test_returns_rects_without_overlap(self):
        pytest.importorskip("ortools")
        from topo2ifc.layout.solver_ortools import OrtoolsSolver

        topo = _make_topo()
        rects = OrtoolsSolver(SolverConfig(seed=42, solver_time_limit_sec=5)).solve(topo)
        assert len(rects) == len(topo.spaces)
        assert check_overlaps(rects) == []


class TestRectTouch:
    def test_horizontal_touch(self):
        a = LayoutRect("a", 0, 0, 5, 4)
        b = LayoutRect("b", 5, 0, 5, 4)
        assert _rects_touch(a, b)

    def test_vertical_touch(self):
        a = LayoutRect("a", 0, 0, 5, 4)
        b = LayoutRect("b", 0, 4, 5, 4)
        assert _rects_touch(a, b)

    def test_no_touch(self):
        a = LayoutRect("a", 0, 0, 2, 2)
        b = LayoutRect("b", 5, 5, 2, 2)
        assert not _rects_touch(a, b)

    def test_overlap_not_touch(self):
        a = LayoutRect("a", 0, 0, 5, 5)
        b = LayoutRect("b", 2, 2, 5, 5)
        # overlapping: x_gap < 0, y_gap < 0 — not "touching"
        assert not _rects_touch(a, b)


class TestSnapToGrid:
    def test_snaps_coordinates(self):
        rects = [LayoutRect("a", 0.123, 0.456, 4.789, 3.111)]
        snapped = snap_to_grid(rects, grid=0.5)
        r = snapped[0]
        assert r.x % 0.5 == pytest.approx(0.0, abs=1e-9)
        assert r.y % 0.5 == pytest.approx(0.0, abs=1e-9)

    def test_zero_size_becomes_grid(self):
        rects = [LayoutRect("a", 0.0, 0.0, 0.0, 0.0)]
        snapped = snap_to_grid(rects, grid=0.5)
        assert snapped[0].width >= 0.5
        assert snapped[0].height >= 0.5


class TestToShapelyPolygons:
    def test_returns_polygons(self):
        rects = [LayoutRect("a", 0, 0, 5, 4), LayoutRect("b", 5, 0, 3, 4)]
        polys = to_shapely_polygons(rects)
        assert set(polys.keys()) == {"a", "b"}
        assert polys["a"].area == pytest.approx(20.0)
