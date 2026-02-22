"""Internal topology data model.

SpaceSpec   – attributes of a single space
AdjacencyEdge  – boundary-sharing relationship
ConnectionEdge – traversal (door) relationship
LayoutRect  – 2-D rectangular placement produced by the Layout Solver
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class SpaceCategory(str, Enum):
    OFFICE = "office"
    MEETING = "meeting"
    CORRIDOR = "corridor"
    TOILET = "toilet"
    ENTRANCE = "entrance"
    CORE = "core"
    STORAGE = "storage"
    GENERIC = "generic"

    @classmethod
    def from_str(cls, value: str) -> "SpaceCategory":
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.GENERIC


# --------------------------------------------------------------------------- #
# Space
# --------------------------------------------------------------------------- #


@dataclass
class SpaceSpec:
    """Specification of a single space node from the RDF graph."""

    space_id: str
    name: str = ""
    category: str = "generic"
    area_target: Optional[float] = None   # m²
    area_min: Optional[float] = None      # m²
    height: Optional[float] = None        # m  (overrides global default)
    aspect_ratio_min: Optional[float] = None
    aspect_ratio_max: Optional[float] = None
    constraints: dict = field(default_factory=dict)

    @property
    def space_category(self) -> SpaceCategory:
        return SpaceCategory.from_str(self.category)

    @property
    def effective_area_min(self) -> float:
        return self.area_min or (self.area_target or 10.0)

    @property
    def effective_area_target(self) -> float:
        return self.area_target or 20.0


# --------------------------------------------------------------------------- #
# Edges
# --------------------------------------------------------------------------- #


@dataclass
class AdjacencyEdge:
    """Two spaces share a physical boundary."""

    space_a: str
    space_b: str


@dataclass
class ConnectionEdge:
    """Two spaces are connected (e.g., through a door)."""

    space_a: str
    space_b: str
    door_width: Optional[float] = None
    door_height: Optional[float] = None


# --------------------------------------------------------------------------- #
# Layout result
# --------------------------------------------------------------------------- #


@dataclass
class LayoutRect:
    """Axis-aligned bounding rectangle produced by the Layout Solver."""

    space_id: str
    x: float          # left edge (m)
    y: float          # bottom edge (m)
    width: float      # m
    height: float     # m

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    def to_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
