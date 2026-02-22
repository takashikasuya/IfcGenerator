"""End-to-end integration tests: RDF → Layout → Geometry → IFC."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_ttl():
    return FIXTURES / "minimal.ttl"


@pytest.fixture
def sbco_ttl():
    return FIXTURES / "sbco_minimal.ttl"


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

    def test_ifc_has_exterior_walls(self, tmp_path, minimal_ttl):
        """Generated IFC should include explicit exterior walls."""
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

        out = tmp_path / "exterior.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )
        ifc2 = ifcopenshell.open(str(out))
        wall_names = [w.Name for w in ifc2.by_type("IfcWall")]
        assert any(n == "ExteriorWall" for n in wall_names)

    def test_ifc_uses_merged_storey_slab(self, tmp_path, minimal_ttl):
        """Generated IFC should use one merged slab for a single-storey layout."""
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

        out = tmp_path / "merged_slab.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )
        ifc2 = ifcopenshell.open(str(out))
        assert len(ifc2.by_type("IfcSlab")) == 1

    def test_ifc_space_profile_is_local_coordinates(self, tmp_path, minimal_ttl):
        """IfcSpace profile origin should be local (no double XY translation)."""
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
        rect_by_id = {r.space_id: r for r in rects}
        name_to_rect = {s.name: rect_by_id[s.space_id] for s in spaces}

        out = tmp_path / "space_local.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )

        ifc2 = ifcopenshell.open(str(out))
        for sp in ifc2.by_type("IfcSpace"):
            rect = name_to_rect.get(sp.Name)
            assert rect is not None
            rep = sp.Representation.Representations[0]
            solid = rep.Items[0]
            profile = solid.SweptArea
            pos = profile.Position.Location.Coordinates
            assert float(pos[0]) == pytest.approx(rect.width / 2.0, abs=1e-6)
            assert float(pos[1]) == pytest.approx(rect.height / 2.0, abs=1e-6)

    def test_ifc_uses_metre_length_unit(self, tmp_path, minimal_ttl):
        """Generated IFC should use metres as the default length unit."""
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

        out = tmp_path / "units.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )

        ifc2 = ifcopenshell.open(str(out))
        length_units = [u for u in ifc2.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"]
        assert len(length_units) == 1
        assert length_units[0].Name == "METRE"
        assert length_units[0].Prefix is None

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


class TestEndToEndSBCO:
    """End-to-end tests using SBCO-vocabulary input."""

    def test_sbco_rdf_to_ifc(self, tmp_path, sbco_ttl):
        """Full pipeline: sbco_minimal.ttl → out.ifc."""
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

        loader = RDFLoader(sbco_ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        adjacencies = loader.extract_adjacencies(g)
        connections = loader.extract_connections(g)

        assert len(spaces) == 3
        assert len(adjacencies) == 2

        topo = TopologyGraph.from_parts(spaces, adjacencies, connections)
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)
        walls = extract_walls(polygons)
        slabs = extract_slabs(polygons)
        doors = extract_doors(polygons, topo.connected_pairs())

        cfg = Config.default()
        out = tmp_path / "sbco_out.ifc"
        IfcExporter(cfg).export(spaces, rects, walls, slabs, doors, out)

        assert out.exists()
        assert out.stat().st_size > 0

        ifc2 = ifcopenshell.open(str(out))
        assert len(ifc2.by_type("IfcSpace")) == 3
        assert len(ifc2.by_type("IfcWall")) > 0
        assert len(ifc2.by_type("IfcSlab")) > 0

    def test_sbco_space_names_in_ifc(self, tmp_path, sbco_ttl):
        """SBCO space names should appear in the generated IFC."""
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

        loader = RDFLoader(sbco_ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)

        out = tmp_path / "sbco_names.ifc"
        IfcExporter(Config.default()).export(
            spaces, rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )
        ifc2 = ifcopenshell.open(str(out))
        names = {sp.Name for sp in ifc2.by_type("IfcSpace")}
        assert "Office Area" in names
        assert "Meeting Room" in names
        assert "Corridor" in names


class TestMultiStoreyEndToEnd:
    """End-to-end tests for multi-storey IFC generation."""

    def test_two_storey_ifc(self, tmp_path):
        """Full pipeline: two_storey.ttl → out.ifc with 2 IfcBuildingStorey."""
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

        ttl = FIXTURES / "two_storey.ttl"
        loader = RDFLoader(ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        adjacencies = loader.extract_adjacencies(g)
        connections = loader.extract_connections(g)

        assert len(spaces) == 5

        topo = TopologyGraph.from_parts(spaces, adjacencies, connections)
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)

        out = tmp_path / "two_storey.ifc"
        IfcExporter(Config.default()).export(
            spaces, rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )

        assert out.exists()
        ifc2 = ifcopenshell.open(str(out))

        # 5 spaces total
        assert len(ifc2.by_type("IfcSpace")) == 5
        # 2 distinct storeys (1F and 2F)
        assert len(ifc2.by_type("IfcBuildingStorey")) == 2

    def test_two_storey_storey_names(self, tmp_path):
        """The two IfcBuildingStorey entities should have distinct names."""
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

        ttl = FIXTURES / "two_storey.ttl"
        loader = RDFLoader(ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)

        out = tmp_path / "two_storey_names.ifc"
        IfcExporter(Config.default()).export(
            spaces, rects,
            extract_walls(polygons),
            extract_slabs(polygons),
            extract_doors(polygons, topo.connected_pairs()),
            out,
        )
        ifc2 = ifcopenshell.open(str(out))
        storey_names = {st.Name for st in ifc2.by_type("IfcBuildingStorey")}
        # Should have 2 unique names
        assert len(storey_names) == 2

    def test_two_storey_walls_assigned_to_each_storey(self, tmp_path):
        """IfcWall instances should be contained in their respective storeys."""
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

        ttl = FIXTURES / "two_storey.ttl"
        loader = RDFLoader(ttl)
        g = loader.load()
        spaces = loader.extract_spaces(g)
        topo = TopologyGraph.from_parts(spaces, loader.extract_adjacencies(g), loader.extract_connections(g))
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)
        space_elevations = {sp.space_id: (sp.storey_elevation or 0.0) for sp in spaces}

        out = tmp_path / "two_storey_walls.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons, space_elevations=space_elevations),
            extract_slabs(polygons, space_elevations=space_elevations),
            extract_doors(polygons, topo.connected_pairs(), space_elevations=space_elevations),
            out,
        )

        ifc2 = ifcopenshell.open(str(out))
        walls_by_storey: dict[str, int] = {}
        for rel in ifc2.by_type("IfcRelContainedInSpatialStructure"):
            storey = rel.RelatingStructure
            if not storey or not storey.is_a("IfcBuildingStorey"):
                continue
            count = sum(1 for elem in rel.RelatedElements if elem.is_a("IfcWall"))
            if count > 0:
                walls_by_storey[storey.GlobalId] = count

        assert len(walls_by_storey) >= 2

    def test_single_storey_mode_preserves_storey_label(self, tmp_path):
        """Single-storey mode should keep a meaningful storey name from RDF."""
        import ifcopenshell

        from topo2ifc.cli import _apply_single_storey_mode
        from topo2ifc.config import Config
        from topo2ifc.geometry.doors import extract_doors
        from topo2ifc.geometry.slabs import extract_slabs
        from topo2ifc.geometry.walls import extract_walls
        from topo2ifc.ifc.exporter import IfcExporter
        from topo2ifc.layout.postprocess import snap_to_grid, to_shapely_polygons
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        from topo2ifc.rdf.loader import RDFLoader
        from topo2ifc.topology.graph import TopologyGraph

        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        adj = loader.extract_adjacencies(g)
        conn = loader.extract_connections(g)
        spaces, adj, conn = _apply_single_storey_mode(spaces, adj, conn)

        topo = TopologyGraph.from_parts(spaces, adj, conn)
        rects = snap_to_grid(HeuristicSolver().solve(topo))
        polygons = to_shapely_polygons(rects)
        space_elevations = {sp.space_id: (sp.storey_elevation or 0.0) for sp in spaces}

        out = tmp_path / "single_storey_label.ifc"
        IfcExporter(Config.default()).export(
            spaces,
            rects,
            extract_walls(polygons, space_elevations=space_elevations),
            extract_slabs(polygons, space_elevations=space_elevations),
            extract_doors(polygons, topo.connected_pairs(), space_elevations=space_elevations),
            out,
        )

        ifc2 = ifcopenshell.open(str(out))
        storey_names = [st.Name for st in ifc2.by_type("IfcBuildingStorey")]
        assert len(storey_names) == 1
        assert storey_names[0]
        assert "1f" in storey_names[0].lower() or storey_names[0] == "Ground Floor"
