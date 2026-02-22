"""Tests for the RDF loader."""

from pathlib import Path

import pytest

from topo2ifc.rdf.loader import RDFLoader
from topo2ifc.topology.model import SpaceCategory

FIXTURES = Path(__file__).parent / "fixtures"


class TestRDFLoader:
    def test_load_parses_graph(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        assert len(g) > 0

    def test_extract_spaces(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        assert len(spaces) == 4

    def test_space_attributes(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        by_name = {s.name: s for s in spaces}
        assert "Room A" in by_name
        room_a = by_name["Room A"]
        assert room_a.area_target == pytest.approx(20.0)
        assert room_a.area_min == pytest.approx(15.0)
        assert room_a.height == pytest.approx(2.8)

    def test_space_category(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        corridor = next(s for s in spaces if s.name == "Corridor")
        assert corridor.space_category == SpaceCategory.CORRIDOR

    def test_extract_adjacencies(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        adjacencies = loader.extract_adjacencies(g)
        assert len(adjacencies) == 3

    def test_extract_connections(self):
        loader = RDFLoader(FIXTURES / "minimal.ttl")
        g = loader.load()
        connections = loader.extract_connections(g)
        assert len(connections) == 3

    def test_missing_file_raises(self):
        loader = RDFLoader("/nonexistent/path.ttl")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_no_spaces_raises(self, tmp_path):
        empty_ttl = tmp_path / "empty.ttl"
        empty_ttl.write_text("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n")
        loader = RDFLoader(empty_ttl)
        g = loader.load()
        with pytest.raises(ValueError, match="No Space nodes"):
            loader.extract_spaces(g)


class TestSBCORDFLoader:
    """Tests for SBCO-vocabulary input (https://github.com/takashikasuya/smartbuiding_ontology)."""

    def test_load_sbco_fixture(self):
        loader = RDFLoader(FIXTURES / "sbco_minimal.ttl")
        g = loader.load()
        assert len(g) > 0

    def test_extract_spaces_sbco(self):
        loader = RDFLoader(FIXTURES / "sbco_minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        assert len(spaces) == 3

    def test_sbco_space_names(self):
        loader = RDFLoader(FIXTURES / "sbco_minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        names = {s.name for s in spaces}
        assert "Office Area" in names
        assert "Meeting Room" in names
        assert "Corridor" in names

    def test_sbco_space_area(self):
        loader = RDFLoader(FIXTURES / "sbco_minimal.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        by_name = {s.name: s for s in spaces}
        assert by_name["Office Area"].area_target == pytest.approx(30.0)
        assert by_name["Meeting Room"].area_min == pytest.approx(12.0)

    def test_sbco_adjacencies(self):
        loader = RDFLoader(FIXTURES / "sbco_minimal.ttl")
        g = loader.load()
        adjacencies = loader.extract_adjacencies(g)
        assert len(adjacencies) == 2


class TestMultiStoreyLoader:
    """Tests for storey extraction and storey membership on spaces."""

    def test_extract_storeys(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        storeys = loader.extract_storeys(g)
        assert len(storeys) == 2

    def test_storey_elevations(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        storeys = loader.extract_storeys(g)
        elevations = {round(s.elevation, 1) for s in storeys}
        assert 0.0 in elevations
        assert 3.0 in elevations

    def test_storey_order(self):
        """Storeys should be sorted by elevation."""
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        storeys = loader.extract_storeys(g)
        elev = [s.elevation for s in storeys]
        assert elev == sorted(elev)

    def test_storey_level_number(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        storeys = loader.extract_storeys(g)
        indices = {s.index for s in storeys if s.index is not None}
        assert 1 in indices
        assert 2 in indices

    def test_spaces_have_storey_id(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        assert all(s.storey_id is not None for s in spaces)

    def test_spaces_have_storey_elevation(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        elevations = {round(s.storey_elevation, 1) for s in spaces if s.storey_elevation is not None}
        assert 0.0 in elevations
        assert 3.0 in elevations

    def test_1f_space_count(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        storeys = loader.extract_storeys(g)
        storey_1f = next(s for s in storeys if round(s.elevation, 1) == 0.0)
        spaces_1f = [sp for sp in spaces if sp.storey_id == storey_1f.storey_id]
        assert len(spaces_1f) == 3

    def test_2f_space_count(self):
        loader = RDFLoader(FIXTURES / "two_storey.ttl")
        g = loader.load()
        spaces = loader.extract_spaces(g)
        storeys = loader.extract_storeys(g)
        storey_2f = next(s for s in storeys if round(s.elevation, 1) == 3.0)
        spaces_2f = [sp for sp in spaces if sp.storey_id == storey_2f.storey_id]
        assert len(spaces_2f) == 2


class TestSBCOEquipmentLoader:
    """Tests for extracting sbco:Equipment entities and locatedIn links."""

    def test_extract_equipment_count(self):
        loader = RDFLoader(FIXTURES / "sbco_equipment.ttl")
        g = loader.load()
        equipment = loader.extract_equipment(g)
        assert len(equipment) == 2

    def test_extract_equipment_space_links(self):
        loader = RDFLoader(FIXTURES / "sbco_equipment.ttl")
        g = loader.load()
        equipment = loader.extract_equipment(g)
        by_name = {e.name: e for e in equipment}

        assert by_name["AHU-01"].space_id == "urn:sbco:space:office"
        assert by_name["VAV-01"].space_id == "urn:sbco:space:meeting"

    def test_extract_equipment_class_type(self):
        loader = RDFLoader(FIXTURES / "sbco_equipment.ttl")
        g = loader.load()
        equipment = loader.extract_equipment(g)
        kinds = {e.equipment_class for e in equipment}
        assert "Equipment" in kinds
        assert "EquipmentExt" in kinds
