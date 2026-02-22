"""IFC model context initialisation.

Creates the IfcProject / IfcSite / IfcBuilding / IfcBuildingStorey hierarchy
and the geometric representation context required for shape representations.
"""

from __future__ import annotations

import math
from typing import Optional

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.owner
import ifcopenshell.api.project
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid


def create_ifc_model(
    project_name: str = "topo2ifc Project",
    storey_elevation: float = 0.0,
) -> tuple[ifcopenshell.file, dict]:
    """Create an IFC4 model with the minimal spatial hierarchy.

    Returns
    -------
    (ifc_file, context_dict) where context_dict contains:
        - ``project``      : IfcProject
        - ``site``         : IfcSite
        - ``building``     : IfcBuilding
        - ``storey``       : IfcBuildingStorey  (ground floor)
        - ``body_context`` : IfcGeometricRepresentationSubContext (Body)
        - ``model_context`` : IfcGeometricRepresentationContext (Model)
    """
    # Create a blank IFC4 file with proper headers
    ifc = ifcopenshell.api.run("project.create_file", version="IFC4")

    # ------------------------------------------------------------------ #
    # Project entity and units
    # ------------------------------------------------------------------ #
    project = ifcopenshell.api.run(
        "root.create_entity", ifc, ifc_class="IfcProject", name=project_name
    )
    length_unit = ifcopenshell.api.run(
        "unit.add_si_unit", ifc, unit_type="LENGTHUNIT"
    )
    area_unit = ifcopenshell.api.run(
        "unit.add_si_unit", ifc, unit_type="AREAUNIT"
    )
    volume_unit = ifcopenshell.api.run(
        "unit.add_si_unit", ifc, unit_type="VOLUMEUNIT"
    )
    ifcopenshell.api.run(
        "unit.assign_unit", ifc, units=[length_unit, area_unit, volume_unit]
    )

    # ------------------------------------------------------------------ #
    # Geometric context
    # ------------------------------------------------------------------ #
    model_ctx = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        ifc,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    # ------------------------------------------------------------------ #
    # Spatial hierarchy  (IFC4: use aggregate.assign_object with products=[...])
    # ------------------------------------------------------------------ #
    site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[site], relating_object=project)

    building = ifcopenshell.api.run(
        "root.create_entity", ifc, ifc_class="IfcBuilding", name="Building"
    )
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[building], relating_object=site)

    storey = ifcopenshell.api.run(
        "root.create_entity",
        ifc,
        ifc_class="IfcBuildingStorey",
        name="Ground Floor",
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", ifc, products=[storey], relating_object=building
    )

    # Set storey elevation via ObjectPlacement (IFC4.3: Elevation is deprecated)
    placement = ifc.createIfcLocalPlacement(
        None,
        ifc.createIfcAxis2Placement3D(
            ifc.createIfcCartesianPoint((0.0, 0.0, storey_elevation)),
            ifc.createIfcDirection((0.0, 0.0, 1.0)),
            ifc.createIfcDirection((1.0, 0.0, 0.0)),
        ),
    )
    storey.ObjectPlacement = placement

    ctx: dict = {
        "project": project,
        "site": site,
        "building": building,
        "storey": storey,
        "body_context": body_ctx,
        "model_context": model_ctx,
    }
    return ifc, ctx


def add_storey(
    ifc: ifcopenshell.file,
    building,
    name: str,
    elevation: float,
) -> object:
    """Add an IfcBuildingStorey to *building* at the given elevation (m).

    The elevation is encoded in the storey's ObjectPlacement Z coordinate,
    following IFC4.3 guidance (Elevation attribute is deprecated).

    Returns the new IfcBuildingStorey entity.
    """
    storey = ifcopenshell.api.run(
        "root.create_entity",
        ifc,
        ifc_class="IfcBuildingStorey",
        name=name,
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", ifc, products=[storey], relating_object=building
    )
    placement = ifc.createIfcLocalPlacement(
        None,
        ifc.createIfcAxis2Placement3D(
            ifc.createIfcCartesianPoint((0.0, 0.0, elevation)),
            ifc.createIfcDirection((0.0, 0.0, 1.0)),
            ifc.createIfcDirection((1.0, 0.0, 0.0)),
        ),
    )
    storey.ObjectPlacement = placement
    return storey
