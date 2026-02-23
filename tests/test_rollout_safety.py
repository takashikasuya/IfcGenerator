import time
from pathlib import Path

from topo2ifc.config import SolverConfig
from topo2ifc.layout.postprocess import check_overlaps
from topo2ifc.layout.solver_heuristic import HeuristicSolver
from topo2ifc.rdf.loader import RDFLoader
from topo2ifc.topology.graph import TopologyGraph

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_topo(path):
    loader = RDFLoader(path)
    g = loader.load()
    return TopologyGraph.from_parts(
        loader.extract_spaces(g),
        loader.extract_adjacencies(g),
        loader.extract_connections(g),
    )


def test_single_storey_golden_bbox_unchanged():
    topo = _load_topo(FIXTURES / "minimal.ttl")

    base = HeuristicSolver(SolverConfig(seed=42, multi_storey_mode=False)).solve(topo)
    trial = HeuristicSolver(SolverConfig(seed=42, multi_storey_mode=True)).solve(topo)

    def bbox(rects):
        min_x = min(r.x for r in rects)
        min_y = min(r.y for r in rects)
        max_x = max(r.x2 for r in rects)
        max_y = max(r.y2 for r in rects)
        return (round(min_x, 4), round(min_y, 4), round(max_x, 4), round(max_y, 4))

    assert bbox(base) == bbox(trial)


def test_multi_core_highrise_overlap_regression_guard():
    topo = _load_topo(FIXTURES / "multi_core_highrise.ttl")
    rects = HeuristicSolver(SolverConfig(seed=42, multi_storey_mode=True)).solve(topo)
    assert check_overlaps(rects) == []


def test_multi_storey_heuristic_performance_acceptance():
    topo = _load_topo(FIXTURES / "six_storey_with_elevator.ttl")

    start = time.perf_counter()
    rects = HeuristicSolver(SolverConfig(seed=42, multi_storey_mode=True)).solve(topo)
    elapsed = time.perf_counter() - start

    assert len(rects) == len(topo.spaces)
    # Acceptance gate for CI: should complete comfortably under this budget.
    assert elapsed < 5.0
