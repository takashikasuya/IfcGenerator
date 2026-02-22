"""Property set helpers for topo2ifc IFC export.

Creates Pset_SpaceCommon and QuantitySet entries for IfcSpace instances.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.pset


def add_space_pset(
    ifc: ifcopenshell.file,
    space_entity,
    category: str = "generic",
    area: float | None = None,
) -> None:
    """Add Pset_SpaceCommon to an IfcSpace entity."""
    pset = ifcopenshell.api.run("pset.add_pset", ifc, product=space_entity, name="Pset_SpaceCommon")

    props: dict = {"OccupancyType": category}
    if area is not None:
        props["NetPlannedArea"] = round(area, 3)

    ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset, properties=props)


def add_quantity_set(
    ifc: ifcopenshell.file,
    element,
    name: str,
    quantities: dict[str, float],
) -> None:
    """Add a simple quantity set to an IFC element."""
    qset = ifcopenshell.api.run("pset.add_qto", ifc, product=element, name=name)
    ifcopenshell.api.run("pset.edit_qto", ifc, qto=qset, properties=quantities)
