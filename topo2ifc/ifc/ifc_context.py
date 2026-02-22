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
        - ``storey``       : IfcBuildingStorey
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
    ifcopenshell.api.run("unit.assign_unit", ifc)

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

    # Set storey elevation
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
