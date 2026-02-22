"""Command-line interface for topo2ifc.

Usage
-----
    topo2ifc --input topology.ttl --output out.ifc
    topo2ifc --input topology.ttl --output out.ifc --solver ortools --seed 42
    topo2ifc --input topology.ttl --output out.ifc --debug /tmp/debug/
"""

from __future__ import annotations

from dataclasses import replace
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from topo2ifc.config import Config, SolverConfig
from topo2ifc.geometry.doors import extract_doors
from topo2ifc.geometry.slabs import extract_slabs
from topo2ifc.geometry.walls import extract_walls
from topo2ifc.ifc.exporter import IfcExporter
from topo2ifc.layout.postprocess import (
    save_layout_geojson,
    save_layout_json,
    snap_to_grid,
    to_shapely_polygons,
)
from topo2ifc.rdf.loader import RDFLoader
from topo2ifc.topology.graph import TopologyGraph
from topo2ifc.topology.model import AdjacencyEdge, ConnectionEdge, SpaceSpec
from topo2ifc.validate.checks import validate_layout, validate_topology
from topo2ifc.validate.reports import (
    build_constraints_report,
    compute_area_deviations,
    save_constraints_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("topo2ifc.cli")


def _apply_single_storey_mode(
    spaces: list[SpaceSpec],
    adjacencies: list[AdjacencyEdge],
    connections: list[ConnectionEdge],
    tol: float = 0.01,
) -> tuple[list[SpaceSpec], list[AdjacencyEdge], list[ConnectionEdge]]:
    """Temporarily keep only the lowest storey and normalize it to 0.0m.

    This is a transitional behavior while multi-storey layout stacking is
    being refined.
    """
    elevations = [s.storey_elevation for s in spaces if s.storey_elevation is not None]
    if not elevations:
        return spaces, adjacencies, connections

    base = min(elevations)
    kept_spaces: list[SpaceSpec] = []
    kept_ids: set[str] = set()
    for sp in spaces:
        elev = sp.storey_elevation
        if elev is None or abs(elev - base) <= tol:
            kept_spaces.append(replace(sp, storey_elevation=0.0))
            kept_ids.add(sp.space_id)

    kept_adj = [
        e for e in adjacencies
        if e.space_a in kept_ids and e.space_b in kept_ids
    ]
    kept_conn = [
        e for e in connections
        if e.space_a in kept_ids and e.space_b in kept_ids
    ]
    return kept_spaces, kept_adj, kept_conn


@click.command()
@click.option("--input", "-i", "input_path", required=True, help="Input RDF topology file (Turtle/JSON-LD)")
@click.option("--output", "-o", "output_path", default="out.ifc", show_default=True, help="Output IFC file path")
@click.option("--config", "-c", "config_path", default=None, help="YAML configuration file")
@click.option("--solver", default="heuristic", show_default=True, type=click.Choice(["heuristic", "ortools"]), help="Layout solver")
@click.option("--seed", default=42, show_default=True, help="Random seed for reproducibility")
@click.option("--debug", "debug_dir", default=None, help="Directory for debug outputs (layout.json, .geojson, report)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(
    input_path: str,
    output_path: str,
    config_path: Optional[str],
    solver: str,
    seed: int,
    debug_dir: Optional[str],
    verbose: bool,
) -> None:
    """Generate an IFC4 model from an RDF topology description."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ---- Configuration ------------------------------------------------ #
    if config_path:
        cfg = Config.from_yaml(config_path)
    else:
        cfg = Config.default()
    cfg.solver.solver = solver
    cfg.solver.seed = seed
    if debug_dir:
        cfg.debug_output_dir = Path(debug_dir)
        cfg.debug_output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load RDF ----------------------------------------------------- #
    logger.info("Loading topology from %s", input_path)
    loader = RDFLoader(input_path)
    g = loader.load()
    spaces = loader.extract_spaces(g)
    adjacencies = loader.extract_adjacencies(g)
    connections = loader.extract_connections(g)
    equipment = loader.extract_equipment(g)
    spaces, adjacencies, connections = _apply_single_storey_mode(
        spaces, adjacencies, connections
    )
    logger.info("Loaded %d spaces, %d adjacencies, %d connections, %d equipment", len(spaces), len(adjacencies), len(connections), len(equipment))

    # ---- Build topology graph ----------------------------------------- #
    topo = TopologyGraph.from_parts(spaces, adjacencies, connections)
    topo_errors = validate_topology(topo)
    if topo_errors:
        for e in topo_errors:
            logger.error("Topology error: %s", e)
        raise SystemExit(1)

    # ---- Layout solver ------------------------------------------------ #
    logger.info("Running layout solver: %s", solver)
    if solver == "ortools":
        from topo2ifc.layout.solver_ortools import OrtoolsSolver
        layout_solver = OrtoolsSolver(cfg.solver)
    else:
        from topo2ifc.layout.solver_heuristic import HeuristicSolver
        layout_solver = HeuristicSolver(cfg.solver)

    rects = layout_solver.solve(topo)
    rects = snap_to_grid(rects, grid=0.05)
    logger.info("Layout generated: %d rectangles", len(rects))

    # ---- Validation --------------------------------------------------- #
    layout_errors = validate_layout(rects, spaces)
    area_devs = compute_area_deviations(rects, spaces)
    report = build_constraints_report(topo_errors, layout_errors, area_devs)

    if layout_errors:
        for e in layout_errors:
            logger.warning("Layout warning: %s", e)

    if cfg.debug_output_dir:
        save_layout_json(rects, cfg.debug_output_dir / "layout.json")
        save_layout_geojson(rects, cfg.debug_output_dir / "layout.geojson")
        save_constraints_report(report, cfg.debug_output_dir / "constraints_report.json")
        logger.info("Debug outputs saved to %s", cfg.debug_output_dir)

    # ---- Geometry ----------------------------------------------------- #
    polygons = to_shapely_polygons(rects)
    space_elevations = {
        sp.space_id: (sp.storey_elevation if sp.storey_elevation is not None else cfg.geometry.storey_elevation)
        for sp in spaces
    }
    walls = extract_walls(
        polygons,
        cfg.geometry.wall_thickness,
        cfg.geometry.wall_height,
        space_elevations=space_elevations,
    )
    slabs = extract_slabs(
        polygons,
        cfg.geometry.storey_elevation,
        cfg.geometry.slab_thickness,
        space_elevations=space_elevations,
    )
    conn_pairs = topo.connected_pairs()
    doors = extract_doors(
        polygons,
        conn_pairs,
        cfg.geometry.door_width,
        cfg.geometry.door_height,
        space_elevations=space_elevations,
    )
    logger.info("Geometry: %d walls, %d slabs, %d doors", len(walls), len(slabs), len(doors))

    # ---- IFC export --------------------------------------------------- #
    exporter = IfcExporter(cfg)
    exporter.export(spaces, rects, walls, slabs, doors, output_path, equipment=equipment)
    logger.info("Done. IFC written to %s", output_path)


if __name__ == "__main__":
    main()
