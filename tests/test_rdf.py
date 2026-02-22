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
