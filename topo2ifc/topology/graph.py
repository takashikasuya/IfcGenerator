"""TopologyGraph – internal NetworkX-backed graph of spaces and edges."""

from __future__ import annotations

import logging
from typing import Iterator

import networkx as nx

from topo2ifc.topology.model import (
    AdjacencyEdge,
    ConnectionEdge,
    SpaceSpec,
)

logger = logging.getLogger(__name__)


class TopologyGraph:
    """Undirected graph where nodes are :class:`SpaceSpec` and edges are
    adjacency / connection relationships.

    The underlying NetworkX graph stores SpaceSpec objects as node attributes
    and edge types as edge attributes so callers can query both.
    """

    def __init__(self) -> None:
        self._g: nx.Graph = nx.Graph()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def add_space(self, spec: SpaceSpec) -> None:
        self._g.add_node(spec.space_id, spec=spec)

    def add_adjacency(self, edge: AdjacencyEdge) -> None:
        self._validate_node(edge.space_a)
        self._validate_node(edge.space_b)
        self._g.add_edge(
            edge.space_a,
            edge.space_b,
            adjacent=True,
            connected=self._g.get_edge_data(edge.space_a, edge.space_b, {}).get(
                "connected", False
            ),
        )

    def add_connection(self, edge: ConnectionEdge) -> None:
        self._validate_node(edge.space_a)
        self._validate_node(edge.space_b)
        existing = self._g.get_edge_data(edge.space_a, edge.space_b, {})
        self._g.add_edge(
            edge.space_a,
            edge.space_b,
            adjacent=existing.get("adjacent", False),
            connected=True,
            door_width=edge.door_width,
            door_height=edge.door_height,
        )

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #

    @property
    def spaces(self) -> list[SpaceSpec]:
        return [data["spec"] for _, data in self._g.nodes(data=True)]

    def get_space(self, space_id: str) -> SpaceSpec:
        return self._g.nodes[space_id]["spec"]

    def adjacent_pairs(self) -> list[tuple[str, str]]:
        return [
            (u, v)
            for u, v, data in self._g.edges(data=True)
            if data.get("adjacent")
        ]

    def connected_pairs(self) -> list[tuple[str, str]]:
        return [
            (u, v)
            for u, v, data in self._g.edges(data=True)
            if data.get("connected")
        ]

    def neighbors(self, space_id: str) -> Iterator[str]:
        return iter(self._g.neighbors(space_id))

    def bfs_order(self, start: str | None = None) -> list[str]:
        """Return nodes in BFS order, starting from *start* (or first node)."""
        if not self._g.nodes:
            return []
        root = start or next(iter(self._g.nodes))
        return list(nx.bfs_tree(self._g, root).nodes)

    def __len__(self) -> int:
        return len(self._g.nodes)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def validate(self) -> list[str]:
        """Return a list of validation error messages (empty = OK)."""
        errors: list[str] = []
        if len(self._g.nodes) == 0:
            errors.append("No spaces defined.")
        return errors

    def _validate_node(self, space_id: str) -> None:
        if space_id not in self._g.nodes:
            raise ValueError(
                f"Space '{space_id}' referenced in edge but not defined as a node."
            )

    # ------------------------------------------------------------------ #
    # Factory
    # ------------------------------------------------------------------ #

    @classmethod
    def from_parts(
        cls,
        spaces: list[SpaceSpec],
        adjacencies: list[AdjacencyEdge],
        connections: list[ConnectionEdge],
    ) -> "TopologyGraph":
        g = cls()
        for s in spaces:
            g.add_space(s)
        for a in adjacencies:
            try:
                g.add_adjacency(a)
            except ValueError as exc:
                logger.warning("Skipping invalid adjacency: %s", exc)
        for c in connections:
            try:
                g.add_connection(c)
            except ValueError as exc:
                logger.warning("Skipping invalid connection: %s", exc)
        return g
