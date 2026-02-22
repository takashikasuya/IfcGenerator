"""RDF predicate / class vocabulary for topo2ifc.

Supports BOT (Building Topology Ontology), Brick and a custom topo2ifc
namespace.  Any of these can be used in input Turtle files.
"""

from rdflib import Namespace, URIRef

# --------------------------------------------------------------------------- #
# Namespaces
# --------------------------------------------------------------------------- #

TOPO = Namespace("https://topo2ifc.example.org/ont#")
BOT = Namespace("https://w3id.org/bot#")
BRICK = Namespace("https://brickschema.org/schema/Brick#")
SCHEMA = Namespace("http://schema.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# --------------------------------------------------------------------------- #
# Classes
# --------------------------------------------------------------------------- #

# Space-like concepts
SPACE_CLASSES: tuple[URIRef, ...] = (
    TOPO.Space,
    BOT.Space,
    BRICK.Space,
    BRICK.Room,
    BRICK.Area,
)

# --------------------------------------------------------------------------- #
# Object Properties
# --------------------------------------------------------------------------- #

# Adjacency (boundary shared, no traversal implied)
ADJACENT_TO: tuple[URIRef, ...] = (
    TOPO.adjacentTo,
    BOT.adjacentElement,
    BRICK.adjacentTo,
)

# Connectivity (traversal possible, e.g. door)
CONNECTED_TO: tuple[URIRef, ...] = (
    TOPO.connectedTo,
    BOT.interfaceOf,
    BRICK.connectedTo,
)

# --------------------------------------------------------------------------- #
# Data Properties
# --------------------------------------------------------------------------- #

PROP_NAME: tuple[URIRef, ...] = (
    TOPO.name,
    RDFS.label,
    SCHEMA.name,
)

PROP_CATEGORY: tuple[URIRef, ...] = (
    TOPO.category,
    BRICK.hasTag,
)

PROP_AREA_TARGET: tuple[URIRef, ...] = (
    TOPO.areaTarget,
    TOPO.targetArea,
    BRICK.area,
)

PROP_AREA_MIN: tuple[URIRef, ...] = (
    TOPO.areaMin,
    TOPO.minArea,
)

PROP_HEIGHT: tuple[URIRef, ...] = (
    TOPO.height,
    BRICK.height,
)

PROP_ASPECT_RATIO_MIN: tuple[URIRef, ...] = (TOPO.aspectRatioMin,)
PROP_ASPECT_RATIO_MAX: tuple[URIRef, ...] = (TOPO.aspectRatioMax,)
