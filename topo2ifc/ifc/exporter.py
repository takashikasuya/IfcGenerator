"""IFC exporter – converts geometry specs into IfcOpenShell entities.

Pipeline
--------
1. Create IFC model + spatial hierarchy  (ifc_context)
2. One IfcBuildingStorey per distinct storey elevation found in the spaces
3. For each space  → IfcSpace  + extruded footprint  (placed in its storey)
4. For each slab   → IfcSlab   + extruded footprint
5. For each wall   → IfcWall   + extruded rectangle
6. For each roof   → IfcRoof   + extruded footprint (at wall top)
7. For each door   → IfcDoor   + position marker
8. Write IFC file
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.geometry
import ifcopenshell.api.spatial
import ifcopenshell.guid

from topo2ifc.config import Config, GeometryConfig
from topo2ifc.geometry.doors import DoorSpec
from topo2ifc.geometry.slabs import SlabSpec
from topo2ifc.geometry.walls import WallSegment
from topo2ifc.ifc.ifc_context import add_storey, create_ifc_model
from topo2ifc.ifc.psets import add_equipment_pset, add_point_pset, add_space_pset
from topo2ifc.topology.model import EquipmentSpec, LayoutRect, PointSpec, SpaceSpec

logger = logging.getLogger(__name__)

# Elevation tolerance for grouping spaces into the same storey (m)
_ELEV_TOL = 0.01


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
        equipment: Optional[list[EquipmentSpec]] = None,
        points: Optional[list[PointSpec]] = None,
    ) -> ifcopenshell.file:
        """Generate the IFC model and write it to *output_path*.

        When spaces carry storey membership (``storey_elevation`` set),
        one IfcBuildingStorey is created per distinct elevation and each
        space is assigned to the correct storey.  When no storey info is
        present all elements are placed on a single ground-floor storey.

        Returns the :class:`ifcopenshell.file` object.
        """
        self.ifc, self._ctx = create_ifc_model(
            storey_elevation=self.geo.storey_elevation,
        )
        ifc = self.ifc
        body_ctx = self._ctx["body_context"]
        building = self._ctx["building"]
        default_storey = self._ctx["storey"]

        rect_by_id = {r.space_id: r for r in rects}
        spaces_by_id = {s.space_id: s for s in spaces}
        spaces_by_elev: dict[float, list[SpaceSpec]] = {}
        for spec in spaces:
            if spec.storey_elevation is None:
                continue
            key = round(spec.storey_elevation, 3)
            spaces_by_elev.setdefault(key, []).append(spec)

        def _name_from_storey_id(storey_id: str) -> str:
            decoded = unquote(storey_id)
            tail = decoded.split("/")[-1]
            return tail or decoded

        # ---- Build storey map ---------------------------------------- #
        # Collect distinct elevations from spaces; fall back to the default storey.
        storey_map: dict[float, object] = {}  # elevation → IfcBuildingStorey

        for spec in spaces:
            elev = spec.storey_elevation
            if elev is None:
                continue
            # Round to avoid floating-point duplicates
            key = round(elev, 3)
            if not any(abs(key - k) < _ELEV_TOL for k in storey_map):
                storey_map[key] = None  # will be created next

        if storey_map:
            # Create one IfcBuildingStorey per distinct elevation.
            # Use the default storey (already created at elevation 0) only if
            # exactly one storey exists at elevation ≈ 0.
            elevations_sorted = sorted(storey_map.keys())
            for i, elev in enumerate(elevations_sorted):
                # Derive a name from elevation
                elev_specs = spaces_by_elev.get(round(elev, 3), [])
                ids = {s.storey_id for s in elev_specs if s.storey_id}
                if len(ids) == 1:
                    name = _name_from_storey_id(next(iter(ids)))
                else:
                    name = f"Level {elev:.1f}m" if elev != 0.0 else "Ground Floor"
                if i == 0 and abs(elev) < _ELEV_TOL:
                    # Reuse the already-created default storey at elevation 0
                    storey_map[elev] = default_storey
                    default_storey.Name = name
                else:
                    storey_map[elev] = add_storey(ifc, building, name, elev)
        else:
            # No storey info → everything goes on the default storey
            storey_map[0.0] = default_storey

        def _get_storey(spec: SpaceSpec):
            """Return the IfcBuildingStorey for *spec*, or the default storey."""
            if spec.storey_elevation is None:
                return default_storey
            key = round(spec.storey_elevation, 3)
            # Find closest key within tolerance
            for k, st in storey_map.items():
                if abs(k - key) < _ELEV_TOL:
                    return st
            return default_storey

        def _get_storey_by_elevation(elevation: float):
            key = round(elevation, 3)
            for k, st in storey_map.items():
                if abs(k - key) < _ELEV_TOL:
                    return st
            return default_storey

        # ---- Spaces -------------------------------------------------- #
        ifc_spaces: dict[str, object] = {}
        for spec in spaces:
            rect = rect_by_id.get(spec.space_id)
            ifc_sp = self._create_space(spec, rect, body_ctx)
            ifc_spaces[spec.space_id] = ifc_sp
            storey = _get_storey(spec)
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
            # Assign slab to the storey matching its elevation
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_slab],
                relating_structure=_get_storey_by_elevation(slab.elevation),
            )

        # ---- Walls --------------------------------------------------- #
        for wall in walls:
            ifc_wall = self._create_wall(wall, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_wall],
                relating_structure=_get_storey_by_elevation(wall.elevation),
            )

        # ---- Roofs --------------------------------------------------- #
        for slab in slabs:
            ifc_roof = self._create_roof(slab, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_roof],
                relating_structure=_get_storey_by_elevation(slab.elevation),
            )

        # ---- Doors --------------------------------------------------- #
        for door in doors:
            ifc_door = self._create_door(door, body_ctx)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_door],
                relating_structure=_get_storey_by_elevation(door.elevation),
            )


        # ---- Equipment ----------------------------------------------- #
        equipment_by_id: dict[str, object] = {}
        equipment_specs_by_id: dict[str, EquipmentSpec] = {eq.equipment_id: eq for eq in (equipment or [])}
        for eq in equipment or []:
            ifc_eq = self._create_equipment(eq, body_ctx, rect_by_id, spaces_by_id)
            target_storey = default_storey
            if eq.space_id and eq.space_id in ifc_spaces:
                ifcopenshell.api.run(
                    "spatial.reference_structure",
                    ifc,
                    products=[ifc_eq],
                    relating_structure=ifc_spaces[eq.space_id],
                )
                spec = spaces_by_id.get(eq.space_id)
                if spec is not None:
                    target_storey = _get_storey(spec)
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_eq],
                relating_structure=target_storey,
            )
            equipment_by_id[eq.equipment_id] = ifc_eq

        point_count_by_equipment: dict[str, int] = {}
        for point in points or []:
            target_storey = default_storey
            placement_x, placement_y, placement_z = 0.0, 0.0, self.geo.storey_elevation
            if point.equipment_id and point.equipment_id in equipment_specs_by_id:
                parent_eq = equipment_specs_by_id[point.equipment_id]
                if parent_eq.space_id and parent_eq.space_id in spaces_by_id:
                    spec = spaces_by_id[parent_eq.space_id]
                    target_storey = _get_storey(spec)
                    placement_z = spec.storey_elevation or 0.0
                    if parent_eq.space_id in rect_by_id:
                        rect = rect_by_id[parent_eq.space_id]
                        placement_x, placement_y = rect.cx, rect.cy

                        count = point_count_by_equipment.get(point.equipment_id, 0)
                        point_count_by_equipment[point.equipment_id] = count + 1
                        offset_step = 0.15
                        placement_x += offset_step * ((count % 3) - 1)
                        placement_y += offset_step * (count // 3)

            ifc_point = self._create_point(point, body_ctx, placement_x, placement_y, placement_z)
            if point.equipment_id and point.equipment_id in equipment_by_id:
                ifcopenshell.api.run(
                    "nest.assign_object",
                    ifc,
                    related_objects=[ifc_point],
                    relating_object=equipment_by_id[point.equipment_id],
                )
            ifcopenshell.api.run(
                "spatial.assign_container",
                ifc,
                products=[ifc_point],
                relating_structure=target_storey,
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
                0.0, 0.0, rect.width, rect.height, height, body_ctx
            )
            ifcopenshell.api.run(
                "geometry.assign_representation",
                ifc,
                product=space,
                representation=shape,
            )
            # Placement at origin of footprint
            placement = self._local_placement(
                rect.x,
                rect.y,
                spec.storey_elevation or 0.0,
            )
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
            name="ExteriorWall" if wall.is_exterior else "PartitionWall",
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
            wall.x1, wall.y1, wall.elevation, angle
        )
        return entity

    # ------------------------------------------------------------------ #
    # Roof
    # ------------------------------------------------------------------ #

    def _create_roof(self, slab: SlabSpec, body_ctx):
        ifc = self.ifc
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcRoof",
            name=f"Roof_{slab.space_id}",
        )
        bounds = slab.polygon.bounds
        x, y = bounds[0], bounds[1]
        w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        thickness = max(0.05, slab.thickness)
        shape = self._extruded_rect_shape(0.0, 0.0, w, h, thickness, body_ctx)
        ifcopenshell.api.run(
            "geometry.assign_representation", ifc, product=entity, representation=shape
        )
        entity.ObjectPlacement = self._local_placement(
            x,
            y,
            slab.elevation + self.geo.wall_height,
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
        entity.ObjectPlacement = self._local_placement_rotated(
            door.x,
            door.y,
            door.elevation,
            angle,
        )
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

    # ------------------------------------------------------------------ #
    # Equipment
    # ------------------------------------------------------------------ #

    def _create_equipment(
        self,
        eq: EquipmentSpec,
        body_ctx,
        rect_by_id: dict[str, LayoutRect],
        spaces_by_id: dict[str, SpaceSpec],
    ):
        ifc = self.ifc
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class="IfcBuildingElementProxy",
            name=eq.name or eq.equipment_id,
        )
        entity.ObjectType = eq.equipment_class

        placement_x, placement_y, placement_z = 0.0, 0.0, self.geo.storey_elevation
        if eq.space_id and eq.space_id in rect_by_id:
            rect = rect_by_id[eq.space_id]
            placement_x, placement_y = rect.cx, rect.cy
        if eq.space_id and eq.space_id in spaces_by_id:
            placement_z = spaces_by_id[eq.space_id].storey_elevation or 0.0

        shape = self._extruded_rect_shape(0.0, 0.0, 0.4, 0.4, 0.4, body_ctx)
        ifcopenshell.api.run(
            "geometry.assign_representation",
            ifc,
            product=entity,
            representation=shape,
        )
        entity.ObjectPlacement = self._local_placement(placement_x, placement_y, placement_z)

        add_equipment_pset(
            ifc,
            entity,
            equipment_class=eq.equipment_class,
            device_type=eq.device_type,
            maintenance_interval=eq.maintenance_interval,
        )
        return entity

    def _create_point(self, point: PointSpec, body_ctx, x: float, y: float, z: float):
        ifc = self.ifc
        ptype = (point.point_type or "").lower()
        ifc_class = "IfcActuator" if (ptype.startswith("cmd") or "command" in ptype) else "IfcSensor"
        entity = ifcopenshell.api.run(
            "root.create_entity",
            ifc,
            ifc_class=ifc_class,
            name=point.name or point.point_id,
        )
        entity.ObjectType = point.point_class

        shape = self._extruded_rect_shape(0.0, 0.0, 0.1, 0.1, 0.1, body_ctx)
        ifcopenshell.api.run(
            "geometry.assign_representation",
            ifc,
            product=entity,
            representation=shape,
        )
        entity.ObjectPlacement = self._local_placement(x, y, z)

        add_point_pset(
            ifc,
            entity,
            point_class=point.point_class,
            point_type=point.point_type,
            unit=point.unit,
            has_quantity=point.has_quantity,
        )
        return entity
