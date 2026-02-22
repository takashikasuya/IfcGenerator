from topo2ifc.validate.reports import build_constraints_report


def test_constraints_report_includes_topology_warnings():
    warnings = [
        {
            "code": "sbco.space.missing_name",
            "severity": "warning",
            "entity_id": "urn:test:space_unnamed",
            "predicate": "https://www.sbco.or.jp/ont/name",
            "message": "SBCO space is missing sbco:name; using URI tail as fallback name.",
        }
    ]

    report = build_constraints_report([], [], {"s1": 1.0}, topology_warnings=warnings)

    assert report["ok"] is True
    assert report["topology_warnings"] == warnings
