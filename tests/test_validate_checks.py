from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import SpaceSpec, VerticalCoreSpec
from topo2ifc.validate.checks import validate_topology


def _topo_with_storey_spaces() -> TopologyGraph:
    return TopologyGraph.from_parts(
        spaces=[
            SpaceSpec("s1", name="S1", storey_id="l1", storey_elevation=0.0),
            SpaceSpec("s2", name="S2", storey_id="l2", storey_elevation=3.0),
        ],
        adjacencies=[],
        connections=[],
    )


def test_validate_topology_requires_stair_for_multi_storey():
    topo = _topo_with_storey_spaces()
    errors = validate_topology(topo, vertical_cores=[])

    assert any("stair" in e.lower() for e in errors)


def test_validate_topology_requires_elevator_for_highrise():
    topo = _topo_with_storey_spaces()
    cores = [VerticalCoreSpec(core_id="stair-1", core_type="stair")]

    errors = validate_topology(
        topo,
        vertical_cores=cores,
        storey_count=6,
        highrise_elevator_threshold=6,
    )

    assert any("elevator" in e.lower() for e in errors)


def test_validate_topology_passes_when_stair_and_elevator_exist():
    topo = _topo_with_storey_spaces()
    cores = [
        VerticalCoreSpec(core_id="stair-1", core_type="stair"),
        VerticalCoreSpec(core_id="elevator-1", core_type="elevator"),
    ]

    errors = validate_topology(
        topo,
        vertical_cores=cores,
        storey_count=6,
        highrise_elevator_threshold=6,
    )

    assert errors == []
