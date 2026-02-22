"""RDF predicate / class vocabulary for topo2ifc.

Supports BOT (Building Topology Ontology), Brick, a custom topo2ifc namespace,
and the Smart Building Co-creation Organization (SBCO) ontology
(https://github.com/takashikasuya/smartbuiding_ontology).
Any of these can be used in input Turtle files.

SBCO hierarchy: Site → Building → Level → Space → Equipment → Point
SBCO terms use the prefix: sbco: <https://www.sbco.or.jp/ont/>

Note: sbco:Equipment and sbco:Point are out-of-scope for the current layout
pipeline (they do not produce floor-plan spaces) and are therefore not included
in SPACE_CLASSES.  Adjacency in SBCO is expressed through containment
(sbco:hasPart / sbco:isPartOf); use BOT or Brick adjacency predicates when
explicit space-to-space adjacency is required.
"""

from rdflib import Namespace, URIRef

# --------------------------------------------------------------------------- #
# Namespaces
# --------------------------------------------------------------------------- #

TOPO = Namespace("https://topo2ifc.example.org/ont#")
BOT = Namespace("https://w3id.org/bot#")
BRICK = Namespace("https://brickschema.org/schema/Brick#")
SBCO = Namespace("https://www.sbco.or.jp/ont/")
SCHEMA = Namespace("http://schema.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# --------------------------------------------------------------------------- #
# Classes
# --------------------------------------------------------------------------- #

# Space-like concepts (sbco:Equipment and sbco:Point are excluded – they do not
# represent floor-plan areas and are out-of-scope for the layout pipeline).
SPACE_CLASSES: tuple[URIRef, ...] = (
    TOPO.Space,
    BOT.Space,
    BRICK.Space,
    BRICK.Room,
    BRICK.Area,
    SBCO.Space,
    SBCO.Room,
    SBCO.Zone,
)

# Storey / floor-level concepts
STOREY_CLASSES: tuple[URIRef, ...] = (
    BOT.Storey,
    BRICK.Floor,
    SBCO.Level,
    TOPO.Storey,
)

# Equipment concepts (Phase 3 pass-through)
EQUIPMENT_CLASSES: tuple[URIRef, ...] = (
    SBCO.Equipment,
    SBCO.EquipmentExt,
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

# Storey → Space containment
HAS_SPACE: tuple[URIRef, ...] = (
    BOT.hasSpace,
    BRICK.hasPart,
    SBCO.hasPart,
    TOPO.hasSpace,
)

# Space → Storey containment (inverse)
IS_PART_OF_STOREY: tuple[URIRef, ...] = (
    BOT.isSpaceOf,
    BRICK.isPartOf,
    SBCO.isPartOf,
    TOPO.isPartOf,
)

# Equipment → Space placement relation
LOCATED_IN: tuple[URIRef, ...] = (
    SBCO.locatedIn,
)

# Building → Storey containment
HAS_STOREY: tuple[URIRef, ...] = (
    BOT.hasStorey,
    TOPO.hasStorey,
)

# --------------------------------------------------------------------------- #
# Data Properties
# --------------------------------------------------------------------------- #

PROP_NAME: tuple[URIRef, ...] = (
    TOPO.name,
    RDFS.label,
    SCHEMA.name,
    SBCO.name,
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

# Storey elevation / level number
PROP_ELEVATION: tuple[URIRef, ...] = (
    TOPO.elevation,
    TOPO.storeyElevation,
    SBCO.elevation,
)

PROP_LEVEL_NUMBER: tuple[URIRef, ...] = (
    TOPO.levelNumber,
    SBCO.levelNumber,
    TOPO.storeyIndex,
)

PROP_STOREY_HEIGHT: tuple[URIRef, ...] = (
    TOPO.storeyHeight,
    TOPO.floorHeight,
    SBCO.storeyHeight,
)


# Equipment data properties
PROP_DEVICE_TYPE: tuple[URIRef, ...] = (
    SBCO.deviceType,
)

PROP_MAINTENANCE_INTERVAL: tuple[URIRef, ...] = (
    SBCO.maintenanceInterval,
)
