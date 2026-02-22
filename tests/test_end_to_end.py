"""End-to-end integration tests: RDF → Layout → Geometry → IFC."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_ttl():
    return FIXTURES / "minimal.ttl"


class TestEndToEnd:
    def test_rdf_to_ifc(self, tmp_path, minimal_ttl):
        """Full pipeline: minimal.ttl → out.ifc."""
        import ifcopenshell

        from topo2ifc.config import Config
        from topo2ifc.geometry.doors import extract_doors
        from topo2ifc.geometry.slabs import extract_slabs
        from topo2ifc.geometry.walls import extract_walls
        from topo2ifc.ifc.exporter import IfcExporter
        from topo2ifc.layout.postprocess import snap_to_grid, to_shapely_polygons
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        from topo2ifc.rdf.loader import RDFLoader
        from topo2ifc.topology.graph import TopologyGraph

        # Load
        loader = RDFLoader(minimal_ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        adjacencies = loader.extract_adjacencies(g)
        connections = loader.extract_connections(g)

        topo = TopologyGraph.from_parts(spaces, adjacencies, connections)

        # Layout
        solver = HeuristicSolver()
        rects = solver.solve(topo)
        rects = snap_to_grid(rects)

        # Geometry
        polygons = to_shapely_polygons(rects)
        walls = extract_walls(polygons)
        slabs = extract_slabs(polygons)
        conn_pairs = topo.connected_pairs()
        doors = extract_doors(polygons, conn_pairs)

        # Export
        cfg = Config.default()
        exporter = IfcExporter(cfg)
        out = tmp_path / "out.ifc"
        ifc = exporter.export(spaces, rects, walls, slabs, doors, out)

        # Verify file written
        assert out.exists()
        assert out.stat().st_size > 0

        # Verify IFC can be re-read
        ifc2 = ifcopenshell.open(str(out))
        ifc_spaces = ifc2.by_type("IfcSpace")
        assert len(ifc_spaces) == 4

    def test_spaces_have_names(self, tmp_path, minimal_ttl):
        """Spaces in the generated IFC should have non-empty names."""
        import ifcopenshell

        from topo2ifc.config import Config
        from topo2ifc.geometry.doors import extract_doors
        from topo2ifc.geometry.slabs import extract_slabs
        from topo2ifc.geometry.walls import extract_walls
        from topo2ifc.ifc.exporter import IfcExporter
        from topo2ifc.layout.postprocess import snap_to_grid, to_shapely_polygons
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        from topo2ifc.rdf.loader import RDFLoader
        from topo2ifc.topology.graph import TopologyGraph

        loader = RDFLoader(minimal_ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)
        ifc = IfcExporter(Config.default()).export(
            spaces, rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            tmp_path / "out.ifc",
        )
        ifc2 = ifcopenshell.open(str(tmp_path / "out.ifc"))
        for sp in ifc2.by_type("IfcSpace"):
            assert sp.Name, f"IfcSpace has no name: {sp}"

    def test_ifc_has_walls_and_slabs(self, tmp_path, minimal_ttl):
        """Generated IFC should contain IfcWall and IfcSlab entities."""
        import ifcopenshell

        from topo2ifc.config import Config
        from topo2ifc.geometry.doors import extract_doors
        from topo2ifc.geometry.slabs import extract_slabs
        from topo2ifc.geometry.walls import extract_walls
        from topo2ifc.ifc.exporter import IfcExporter
        from topo2ifc.layout.postprocess import snap_to_grid, to_shapely_polygons
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        from topo2ifc.rdf.loader import RDFLoader
        from topo2ifc.topology.graph import TopologyGraph

        loader = RDFLoader(minimal_ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)

        out = tmp_path / "out.ifc"
        IfcExporter(Config.default()).export(
            spaces, rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )
        ifc2 = ifcopenshell.open(str(out))
        assert len(ifc2.by_type("IfcWall")) > 0
        assert len(ifc2.by_type("IfcSlab")) > 0

    def test_seed_reproducibility(self, tmp_path, minimal_ttl):
        """Same seed should produce same number of walls."""
        import ifcopenshell

        from topo2ifc.config import Config, SolverConfig
        from topo2ifc.geometry.doors import extract_doors
        from topo2ifc.geometry.slabs import extract_slabs
        from topo2ifc.geometry.walls import extract_walls
        from topo2ifc.ifc.exporter import IfcExporter
        from topo2ifc.layout.postprocess import snap_to_grid, to_shapely_polygons
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        from topo2ifc.rdf.loader import RDFLoader
        from topo2ifc.topology.graph import TopologyGraph

        def run(seed: int) -> int:
            loader = RDFLoader(minimal_ttl)
            g = loader.load()
            spaces = loader.extract_spaces(g)
            topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
            rects = snap_to_grid(HeuristicSolver(SolverConfig(seed=seed)).solve(topo))
            polygons = to_shapely_polygons(rects)
            out = tmp_path / f"out_{seed}.ifc"
            IfcExporter(Config.default()).export(
                spaces, rects,
                extract_walls(polygons),
                extract_slabs(polygons),
                extract_doors(polygons, topo.connected_pairs()),
                out,
            )
            ifc2 = ifcopenshell.open(str(out))
            return len(ifc2.by_type("IfcWall"))

        assert run(42) == run(42)
