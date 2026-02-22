"""IFC exporter – converts geometry specs into IfcOpenShell entities.

Pipeline
--------
1. Create IFC model + spatial hierarchy  (ifc_context)
2. For each space  → IfcSpace  + extruded footprint
3. For each slab   → IfcSlab   + extruded footprint
4. For each wall   → IfcWall   + extruded rectangle
5. For each door   → IfcDoor   + position marker
6. Write IFC file
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.geometry
import ifcopenshell.api.spatial
import ifcopenshell.guid

from topo2ifc.config import Config, GeometryConfig
from topo2ifc.geometry.doors import DoorSpec
from topo2ifc.geometry.slabs import SlabSpec
from topo2ifc.geometry.walls import WallSegment
from topo2ifc.ifc.ifc_context import create_ifc_model
from topo2ifc.ifc.psets import add_space_pset
from topo2ifc.topology.model import LayoutRect, SpaceSpec

logger = logging.getLogger(__name__)


class IfcExporter:
    """Assemble an IFC4 model and write it to disk."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.cfg = config or Config()
        self.geo = self.cfg.geometry
        self.ifc: Optional[ifcopenshell.file] = None
        self._ctx: dict = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def export(
        self,
        spaces: list[SpaceSpec],
        rects: list[LayoutRect],
        walls: list[WallSegment],
        slabs: list[SlabSpec],
        doors: list[DoorSpec],
        output_path: str | Path,
    ) -> ifcopenshell.file:
        """Generate the IFC model and write it to *output_path*.

        Returns the :class:`ifcopenshell.file` object.
        """
        self.ifc, self._ctx = create_ifc_model(
            storey_elevation=self.geo.storey_elevation,
        )
        ifc = self.ifc
        storey = self._ctx["storey"]
        body_ctx = self._ctx["body_context"]

        rect_by_id = {r.space_id: r for r in rects}
        spec_by_id = {s.space_id: s for s in spaces}

        # ---- Spaces -------------------------------------------------- #
        ifc_spaces: dict[str, object] = {}
        for spec in spaces:
            rect = rect_by_id.get(spec.space_id)
            ifc_sp = self._create_space(spec, rect, body_ctx)
            ifc_spaces[spec.space_id] = ifc_sp
            # IfcSpace is a spatial element → use aggregate.assign_object
            ifcopenshell.api.run(
                "aggregate.assign_object",
                ifc,
                products=[ifc_sp],
                relating_object=storey,
            )

        # ---- Slabs --------------------------------------------------- #
        for slab in slabs:
            ifc_slab = self._create_slab(slab, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_slab],
                relating_structure=storey,
            )

        # ---- Walls --------------------------------------------------- #
        for wall in walls:
            ifc_wall = self._create_wall(wall, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_wall],
                relating_structure=storey,
            )

        # ---- Doors --------------------------------------------------- #
        for door in doors:
            ifc_door = self._create_door(door, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_door],
                relating_structure=storey,
            )

        ifc.write(str(output_path))
        logger.info("IFC written → %s", output_path)
        return ifc

    # ------------------------------------------------------------------ #
    # Space
    # ------------------------------------------------------------------ #

    def _create_space(
        self,
        spec: SpaceSpec,
        rect: Optional[LayoutRect],
        body_ctx,
    ):
        ifc = self.ifc
        space = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcSpace",
            name=spec.name or spec.space_id,
        )
        space.LongName = spec.name or spec.space_id

        if rect is not None:
            # 2-D footprint extruded to wall height
            height = spec.height or self.geo.wall_height
            shape = self._extruded_rect_shape(
                rect.x, rect.y, rect.width, rect.height, height, body_ctx
            )
            ifcopenshell.api.run(
                "geometry.assign_representation",
                ifc,
                product=space,
                representation=shape,
            )
            # Placement at origin of footprint
            placement = self._local_placement(rect.x, rect.y, 0.0)
            space.ObjectPlacement = placement

        add_space_pset(ifc, space, category=spec.category, area=rect.area if rect else None)
        return space

    # ------------------------------------------------------------------ #
    # Slab
    # ------------------------------------------------------------------ #

    def _create_slab(self, slab: SlabSpec, body_ctx):
        ifc = self.ifc
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcSlab",
            name=f"Slab_{slab.space_id}",
        )
        bounds = slab.polygon.bounds  # (minx, miny, maxx, maxy)
        x, y = bounds[0], bounds[1]
        w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        shape = self._extruded_rect_shape(0.0, 0.0, w, h, slab.thickness, body_ctx)
        ifcopenshell.api.run(
            "geometry.assign_representation", ifc, product=entity, representation=shape
        )
        entity.ObjectPlacement = self._local_placement(x, y, slab.elevation - slab.thickness)
        return entity

    # ------------------------------------------------------------------ #
    # Wall
    # ------------------------------------------------------------------ #

    def _create_wall(self, wall: WallSegment, body_ctx):
        ifc = self.ifc
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcWall",
            name="Wall",
        )
        # Wall profile: rectangle (length × thickness), extruded to height
        length = wall.length
        if length < 1e-6:
            length = 1e-3
        shape = self._extruded_rect_shape(
            0.0, 0.0, length, wall.thickness, wall.height, body_ctx
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", ifc, product=entity, representation=shape
        )
        # Placement: origin at wall start, rotated along wall direction
        dx, dy = wall.direction
        angle = math.atan2(dy, dx)
        entity.ObjectPlacement = self._local_placement_rotated(
            wall.x1, wall.y1, 0.0, angle
        )
        return entity

    # ------------------------------------------------------------------ #
    # Door
    # ------------------------------------------------------------------ #

    def _create_door(self, door: DoorSpec, body_ctx):
        ifc = self.ifc
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcDoor",
            name=f"Door_{door.space_a}_{door.space_b}",
        )
        entity.OverallWidth = door.width
        entity.OverallHeight = door.height
        # Simple box representation
        shape = self._extruded_rect_shape(
            0.0, 0.0, door.width, 0.1, door.height, body_ctx
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", ifc, product=entity, representation=shape
        )
        angle = math.radians(door.angle)
        entity.ObjectPlacement = self._local_placement_rotated(door.x, door.y, 0.0, angle)
        return entity

    # ------------------------------------------------------------------ #
    # Geometry helpers
    # ------------------------------------------------------------------ #

    def _extruded_rect_shape(
        self,
        x: float,
        y: float,
        width: float,
        depth: float,
        height: float,
        context,
    ):
        """Return an IfcShapeRepresentation with a single extruded rectangle."""
        ifc = self.ifc
        # Rectangle profile at (x, y), width × depth
        profile = ifc.createIfcRectangleProfileDef(
            "AREA",
            None,
            ifc.createIfcAxis2Placement2D(
                ifc.createIfcCartesianPoint((x + width / 2, y + depth / 2)),
                ifc.createIfcDirection((1.0, 0.0)),
            ),
            width,
            depth,
        )
        extrusion_dir = ifc.createIfcDirection((0.0, 0.0, 1.0))
        position = ifc.createIfcAxis2Placement3D(
            ifc.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ifc.createIfcDirection((0.0, 0.0, 1.0)),
            ifc.createIfcDirection((1.0, 0.0, 0.0)),
        )
        solid = ifc.createIfcExtrudedAreaSolid(profile, position, extrusion_dir, height)
        shape_rep = ifc.createIfcShapeRepresentation(
            context,
            "Body",
            "SweptSolid",
            [solid],
        )
        return shape_rep

    def _local_placement(self, x: float, y: float, z: float):
        ifc = self.ifc
        return ifc.createIfcLocalPlacement(
            None,
            ifc.createIfcAxis2Placement3D(
                ifc.createIfcCartesianPoint((x, y, z)),
                ifc.createIfcDirection((0.0, 0.0, 1.0)),
                ifc.createIfcDirection((1.0, 0.0, 0.0)),
            ),
        )

    def _local_placement_rotated(self, x: float, y: float, z: float, angle_rad: float):
        ifc = self.ifc
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return ifc.createIfcLocalPlacement(
            None,
            ifc.createIfcAxis2Placement3D(
                ifc.createIfcCartesianPoint((x, y, z)),
                ifc.createIfcDirection((0.0, 0.0, 1.0)),
                ifc.createIfcDirection((cos_a, sin_a, 0.0)),
            ),
        )
