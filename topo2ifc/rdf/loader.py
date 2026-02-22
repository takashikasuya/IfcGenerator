"""RDF topology loader.

Reads a Turtle / JSON-LD file with rdflib and converts it into the internal
:class:`topo2ifc.topology.graph.TopologyGraph` representation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF as RDF_NS

from topo2ifc.rdf import vocabulary as V
from topo2ifc.topology.model import AdjacencyEdge, ConnectionEdge, SpaceSpec

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper: first matching predicate value
# --------------------------------------------------------------------------- #


def _first_literal(g: Graph, subject: URIRef, predicates: tuple) -> Optional[str]:
    for pred in predicates:
        for obj in g.objects(subject, pred):
            if isinstance(obj, Literal):
                return str(obj)
    return None


def _first_float(g: Graph, subject: URIRef, predicates: tuple) -> Optional[float]:
    raw = _first_literal(g, subject, predicates)
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return None


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


class RDFLoader:
    """Load an RDF file and convert it to internal topology structures."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._graph: Optional[Graph] = None

    def load(self) -> Graph:
        """Parse the RDF file and return the raw rdflib Graph."""
        g = Graph()
        fmt = _detect_format(self.path)
        g.parse(str(self.path), format=fmt)
        logger.debug("Loaded %d triples from %s", len(g), self.path)
        self._graph = g
        return g

    # ------------------------------------------------------------------ #
    # Space extraction
    # ------------------------------------------------------------------ #

    def extract_spaces(self, g: Optional[Graph] = None) -> list[SpaceSpec]:
        """Return a :class:`SpaceSpec` for every Space node in the graph."""
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_spaces()")

        spaces: list[SpaceSpec] = []
        seen: set[str] = set()

        for space_class in V.SPACE_CLASSES:
            for subject in g.subjects(RDF_NS.type, space_class):
                sid = str(subject)
                if sid in seen:
                    continue
                seen.add(sid)

                name = _first_literal(g, subject, V.PROP_NAME)
                category = _first_literal(g, subject, V.PROP_CATEGORY)
                area_target = _first_float(g, subject, V.PROP_AREA_TARGET)
                area_min = _first_float(g, subject, V.PROP_AREA_MIN)
                height = _first_float(g, subject, V.PROP_HEIGHT)
                ar_min = _first_float(g, subject, V.PROP_ASPECT_RATIO_MIN)
                ar_max = _first_float(g, subject, V.PROP_ASPECT_RATIO_MAX)

                spaces.append(
                    SpaceSpec(
                        space_id=sid,
                        name=name or sid.split("#")[-1].split("/")[-1],
                        category=category or "generic",
                        area_target=area_target,
                        area_min=area_min,
                        height=height,
                        aspect_ratio_min=ar_min,
                        aspect_ratio_max=ar_max,
                    )
                )

        if not spaces:
            raise ValueError(f"No Space nodes found in {self.path}")

        logger.debug("Extracted %d spaces", len(spaces))
        return spaces

    # ------------------------------------------------------------------ #
    # Edge extraction
    # ------------------------------------------------------------------ #

    def extract_adjacencies(
        self,
        g: Optional[Graph] = None,
    ) -> list[AdjacencyEdge]:
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_adjacencies()")

        edges: list[AdjacencyEdge] = []
        seen: set[tuple[str, str]] = set()

        for pred in V.ADJACENT_TO:
            for subj, obj in g.subject_objects(pred):
                a, b = str(subj), str(obj)
                key = (min(a, b), max(a, b))
                if key not in seen:
                    seen.add(key)
                    edges.append(AdjacencyEdge(space_a=a, space_b=b))

        return edges

    def extract_connections(
        self,
        g: Optional[Graph] = None,
    ) -> list[ConnectionEdge]:
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_connections()")

        edges: list[ConnectionEdge] = []
        seen: set[tuple[str, str]] = set()

        for pred in V.CONNECTED_TO:
            for subj, obj in g.subject_objects(pred):
                a, b = str(subj), str(obj)
                key = (min(a, b), max(a, b))
                if key not in seen:
                    seen.add(key)
                    edges.append(ConnectionEdge(space_a=a, space_b=b))

        return edges


# --------------------------------------------------------------------------- #
# Format detection
# --------------------------------------------------------------------------- #


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".ttl": "turtle",
        ".turtle": "turtle",
        ".jsonld": "json-ld",
        ".json": "json-ld",
        ".n3": "n3",
        ".nt": "nt",
        ".xml": "xml",
        ".rdf": "xml",
    }
    return mapping.get(suffix, "turtle")
