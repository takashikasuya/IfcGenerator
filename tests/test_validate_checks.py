from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import LayoutRect, SpaceSpec, VerticalCoreSpec
from topo2ifc.validate.checks import validate_shaft_openings, validate_topology


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


def test_validate_shaft_openings_rejects_non_positive_sizes():
    errors = validate_shaft_openings(
        {0.0: LayoutRect("open", x=0.0, y=0.0, width=0.0, height=1.0)}
    )
    assert any("non-positive" in e for e in errors)


def test_validate_shaft_openings_rejects_size_mismatch_between_levels():
    errors = validate_shaft_openings(
        {
            0.0: LayoutRect("open_l1", x=0.0, y=0.0, width=1.0, height=1.0),
            3.0: LayoutRect("open_l2", x=0.0, y=0.0, width=1.2, height=1.0),
        }
    )
    assert any("mismatch" in e.lower() for e in errors)
