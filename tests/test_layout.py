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
