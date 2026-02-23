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
from topo2ifc.topology.model import (
    AdjacencyEdge,
    CirculationSpec,
    ConnectionEdge,
    EquipmentSpec,
    PointSpec,
    SpaceSpec,
    StoreySpec,
    VerticalCoreSpec,
)

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


def _first_int(g: Graph, subject: URIRef, predicates: tuple) -> Optional[int]:
    raw = _first_literal(g, subject, predicates)
    if raw is not None:
        try:
            return int(raw)
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
        self._warnings: list[dict[str, str]] = []
        self._warning_keys: set[tuple[str, str, str]] = set()

    def get_warnings(self) -> list[dict[str, str]]:
        """Return structured extraction warnings collected so far."""
        return list(self._warnings)

    def _add_warning(
        self,
        code: str,
        entity_id: str,
        predicate: str,
        message: str,
    ) -> None:
        key = (code, entity_id, predicate)
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self._warnings.append(
            {
                "code": code,
                "severity": "warning",
                "entity_id": entity_id,
                "predicate": predicate,
                "message": message,
            }
        )

    def load(self) -> Graph:
        """Parse the RDF file and return the raw rdflib Graph."""
        self._warnings.clear()
        self._warning_keys.clear()
        g = Graph()
        fmt = _detect_format(self.path)
        g.parse(str(self.path), format=fmt)
        logger.debug("Loaded %d triples from %s", len(g), self.path)
        self._graph = g
        return g

    # ------------------------------------------------------------------ #
    # Storey extraction
    # ------------------------------------------------------------------ #

    def extract_storeys(self, g: Optional[Graph] = None) -> list[StoreySpec]:
        """Return a :class:`StoreySpec` for every Storey/Level node in the graph."""
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_storeys()")

        storeys: list[StoreySpec] = []
        seen: set[str] = set()

        for storey_class in V.STOREY_CLASSES:
            for subject in g.subjects(RDF_NS.type, storey_class):
                sid = str(subject)
                if sid in seen:
                    continue
                seen.add(sid)

                name = _first_literal(g, subject, V.PROP_NAME)
                elevation = _first_float(g, subject, V.PROP_ELEVATION) or 0.0
                storey_height = _first_float(g, subject, V.PROP_STOREY_HEIGHT) or 0.0
                index = _first_int(g, subject, V.PROP_LEVEL_NUMBER)

                storeys.append(
                    StoreySpec(
                        storey_id=sid,
                        name=name or sid.split("#")[-1].split("/")[-1],
                        elevation=elevation,
                        storey_height=storey_height,
                        index=index,
                    )
                )

        # Sort by elevation (then index) for deterministic ordering
        storeys.sort(key=lambda s: (s.elevation, s.index or 0))
        logger.debug("Extracted %d storeys", len(storeys))
        return storeys

    # ------------------------------------------------------------------ #
    # Space extraction
    # ------------------------------------------------------------------ #

    def extract_spaces(self, g: Optional[Graph] = None) -> list[SpaceSpec]:
        """Return a :class:`SpaceSpec` for every Space node in the graph.

        If storey membership is encoded via containment predicates
        (sbco:isPartOf, bot:isSpaceOf, brick:isPartOf, etc.) the
        ``storey_id`` and ``storey_elevation`` fields are populated
        automatically.
        """
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_spaces()")

        # Build a map from storey URI → StoreySpec for elevation look-up
        storey_specs = self.extract_storeys(g)
        storey_by_id: dict[str, StoreySpec] = {s.storey_id: s for s in storey_specs}

        # Also build reverse map: space_uri → storey_uri via hasPart predicates
        space_to_storey: dict[str, str] = {}
        for pred in V.HAS_SPACE:
            for storey_uri, space_uri in g.subject_objects(pred):
                space_to_storey[str(space_uri)] = str(storey_uri)
        for pred in V.IS_PART_OF_STOREY:
            for space_uri, storey_uri in g.subject_objects(pred):
                if str(storey_uri) in storey_by_id:
                    space_to_storey[str(space_uri)] = str(storey_uri)

        spaces: list[SpaceSpec] = []
        seen: set[str] = set()

        for space_class in V.SPACE_CLASSES:
            for subject in g.subjects(RDF_NS.type, space_class):
                sid = str(subject)
                if sid in seen:
                    continue
                seen.add(sid)

                name = _first_literal(g, subject, V.PROP_NAME)
                if space_class == V.SBCO.Space and name is None:
                    self._add_warning(
                        code="sbco.space.missing_name",
                        entity_id=sid,
                        predicate=str(V.SBCO.name),
                        message="SBCO space is missing sbco:name; using URI tail as fallback name.",
                    )
                category = _first_literal(g, subject, V.PROP_CATEGORY)
                area_target = _first_float(g, subject, V.PROP_AREA_TARGET)
                area_min = _first_float(g, subject, V.PROP_AREA_MIN)
                height = _first_float(g, subject, V.PROP_HEIGHT)
                ar_min = _first_float(g, subject, V.PROP_ASPECT_RATIO_MIN)
                ar_max = _first_float(g, subject, V.PROP_ASPECT_RATIO_MAX)

                storey_id = space_to_storey.get(sid)
                storey_elevation: Optional[float] = None
                if storey_id and storey_id in storey_by_id:
                    storey_elevation = storey_by_id[storey_id].elevation

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
                        storey_id=storey_id,
                        storey_elevation=storey_elevation,
                    )
                )

        if not spaces:
            raise ValueError(f"No Space nodes found in {self.path}")

        logger.debug("Extracted %d spaces", len(spaces))
        return spaces

    # ------------------------------------------------------------------ #
    # Edge extraction
    # ------------------------------------------------------------------ #

    def extract_equipment(self, g: Optional[Graph] = None) -> list[EquipmentSpec]:
        """Return a :class:`EquipmentSpec` for every SBCO equipment node."""
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_equipment()")

        equipment_list: list[EquipmentSpec] = []
        seen: set[str] = set()

        for equipment_class in V.EQUIPMENT_CLASSES:
            for subject in g.subjects(RDF_NS.type, equipment_class):
                eid = str(subject)
                if eid in seen:
                    continue
                seen.add(eid)

                name = _first_literal(g, subject, V.PROP_NAME)
                space_id: Optional[str] = None
                for pred in V.LOCATED_IN:
                    for obj in g.objects(subject, pred):
                        space_id = str(obj)
                        break
                    if space_id:
                        break

                device_type = _first_literal(g, subject, V.PROP_DEVICE_TYPE)
                maintenance_interval = _first_literal(g, subject, V.PROP_MAINTENANCE_INTERVAL)

                equipment_list.append(
                    EquipmentSpec(
                        equipment_id=eid,
                        name=name or eid.split("#")[-1].split("/")[-1],
                        space_id=space_id,
                        equipment_class=str(equipment_class).split("#")[-1].split("/")[-1],
                        device_type=device_type,
                        maintenance_interval=maintenance_interval,
                    )
                )

        return equipment_list

    def extract_points(self, g: Optional[Graph] = None) -> list[PointSpec]:
        """Return a :class:`PointSpec` for every SBCO point node."""
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_points()")

        points: list[PointSpec] = []
        seen: set[str] = set()

        equipment_ids = {str(s) for cls in V.EQUIPMENT_CLASSES for s in g.subjects(RDF_NS.type, cls)}

        point_to_equipment: dict[str, str] = {}
        for pred in V.HAS_POINT:
            for subj, obj in g.subject_objects(pred):
                sid, oid = str(subj), str(obj)
                if sid in equipment_ids:
                    point_to_equipment[oid] = sid

        for point_class in V.POINT_CLASSES:
            for subject in g.subjects(RDF_NS.type, point_class):
                pid = str(subject)
                if pid in seen:
                    continue
                seen.add(pid)

                name = _first_literal(g, subject, V.PROP_NAME)
                points.append(
                    PointSpec(
                        point_id=pid,
                        name=name or pid.split("#")[-1].split("/")[-1],
                        equipment_id=point_to_equipment.get(pid),
                        point_class=str(point_class).split("#")[-1].split("/")[-1],
                        point_type=_first_literal(g, subject, V.PROP_POINT_TYPE),
                        unit=_first_literal(g, subject, V.PROP_UNIT),
                        has_quantity=_first_literal(g, subject, V.PROP_HAS_QUANTITY),
                    )
                )

        return points

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

    def extract_circulation(self, g: Optional[Graph] = None) -> list[CirculationSpec]:
        """Return stairs/elevators extracted as :class:`CirculationSpec`."""
        g = g or self._graph
        if g is None:
            raise RuntimeError("Call load() before extract_circulation()")

        circulation: list[CirculationSpec] = []
        seen: set[str] = set()

        for circulation_class in V.CIRCULATION_CLASSES:
            class_name = str(circulation_class).split("#")[-1].split("/")[-1].lower()
            for subject in g.subjects(RDF_NS.type, circulation_class):
                cid = str(subject)
                if cid in seen:
                    continue
                seen.add(cid)

                name = _first_literal(g, subject, V.PROP_NAME)
                space_id: Optional[str] = None
                space_ids: list[str] = []
                for pred in V.LOCATED_IN:
                    for obj in g.objects(subject, pred):
                        space_ids.append(str(obj))
                if space_ids:
                    space_id = space_ids[0]
                    if len(space_ids) > 1:
                        logger.warning(
                            "Circulation element %s has multiple LOCATED_IN spaces (%s); using first: %s",
                            cid,
                            ", ".join(space_ids),
                            space_id,
                        )

                circulation.append(
                    CirculationSpec(
                        circulation_id=cid,
                        circulation_type=class_name,
                        name=name or cid.split("#")[-1].split("/")[-1],
                        space_id=space_id,
                    )
                )

        logger.debug("Extracted %d circulation elements", len(circulation))
        return circulation

    def extract_vertical_cores(self, g: Optional[Graph] = None) -> list[VerticalCoreSpec]:
        """Return vertical core requirements derived from circulation entities."""
        circulation = self.extract_circulation(g)
        return [
            VerticalCoreSpec(
                core_id=spec.circulation_id,
                core_type=spec.circulation_type,
                name=spec.name,
                space_id=spec.space_id,
            )
            for spec in circulation
        ]

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
