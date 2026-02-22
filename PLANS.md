# PLANS.md

Development plan for the IfcGenerator (`topo2ifc`) project.
AI agents must read this file before starting work and mark each task `[x]` when complete.

---

## Hotfix – IFC geometry visibility

### H-1 Fix IFC project length unit (mm → m)
- [x] Add a regression test ensuring exported IFC uses `IfcSIUnit` length in metres (no `MILLI` prefix).
- [x] Update IFC context setup to assign metre-based project units explicitly.
- [x] Validate that generated geometry remains visible in standard IFC viewers.

### H-2 Fix multi-storey layout and geometry placement
- [x] Fix heuristic layout ordering so disconnected topology components are all placed.
- [x] Propagate per-space storey elevation into slab/wall/door geometry specs.
- [x] Place and container-assign walls/doors/slabs to the correct `IfcBuildingStorey`.
- [x] Add regression tests for disconnected layout and multi-storey wall placement.

### H-3 Improve building-like layout compactness
- [x] Replace fixed-width strip packing with dynamic compact packing based on target total area.
- [x] Add regression test ensuring many disconnected spaces are not all placed in a single row.
- [x] Validate sample IFC generation now produces a more compact floor layout.

### H-4 Temporary single-storey mode and layout refinement
- [x] In CLI pipeline, omit spaces above the lowest detected storey elevation (temporary single-storey behavior).
- [x] Normalize retained storey elevation to 0.0m so exported IFC is handled as a single-storey building.
- [x] Refine heuristic placement for sparse/disconnected topology using compact grid placement.
- [x] Add tests for single-storey filtering and sparse-layout compactness behavior.

### H-5 Restore spatial hierarchy labels in single-storey mode
- [x] Keep original `storey_id` when single-storey filtering is applied.
- [x] Derive `IfcBuildingStorey.Name` from retained RDF storey identifier when available.
- [x] Add regression tests for single-storey storey-label preservation.

### H-6 Layout/Geometry quality overhaul
- [x] Rebuild wall extraction to guarantee building envelope (exterior walls) and interior partitions from shared boundaries.
- [x] Change slab generation to per-storey merged slabs so all spaces are on a continuous slab.
- [x] Strengthen OR-Tools CP-SAT objective with compactness and topology-aware proximity terms.
- [x] Add regression tests for exterior wall presence and merged slab coverage.

### H-7 Fix space placement relative to slab
- [x] Add regression test to ensure IfcSpace profile is local (not globally offset twice).
- [x] Fix IfcSpace geometry creation to avoid double XY translation.
- [x] Validate that generated spaces sit on the merged slab footprint.

### H-8 Fix wall length degeneration and add roof
- [x] Fix wall segment extraction so closed boundary lines are split into meaningful edges.
- [x] Improve shared-boundary extraction to avoid near-zero wall artifacts.
- [x] Export rooftop geometry (`IfcRoof`) for each storey slab footprint.
- [x] Add regression tests for non-degenerate wall lengths and roof existence.

---

## Phase 1 – SBCO Vocabulary Support

### 1-1 Add SBCO namespace and classes to `vocabulary.py`
- [x] Add `SBCO = Namespace("https://www.sbco.or.jp/ont/")` to `topo2ifc/rdf/vocabulary.py`.
- [x] Add `sbco:Space` to `SPACE_CLASSES`.
- [x] Add `sbco:adjacentTo` (if present in SBCO) to `ADJACENT_TO`; otherwise document that `sbco:hasPart` / `sbco:isPartOf` encode containment (not adjacency) and leave adjacency to BOT/Brick.
- [x] Add `sbco:name` to `PROP_NAME`.
- [x] Confirm that `sbco:Equipment` and `sbco:Point` are out-of-scope for the current layout pipeline (they do not produce spaces) and document this in a comment.

### 1-2 Add SBCO fixture and tests
- [x] Create `tests/fixtures/sbco_minimal.ttl` – a minimal Turtle file using only SBCO vocabulary (`sbco:Space`, `sbco:name`, `sbco:hasPart`, `sbco:isPartOf`) to describe a simple `Level` with three spaces.
- [x] Add a test class `TestSBCORDFLoader` in `tests/test_rdf.py` that:
  - loads `sbco_minimal.ttl`,
  - asserts the correct number of spaces are extracted,
  - asserts space names are extracted correctly.

### 1-3 Validate end-to-end with SBCO input
- [x] Run `topo2ifc --input tests/fixtures/sbco_minimal.ttl --output /tmp/sbco_test.ifc` and confirm IFC is produced without errors.
- [x] Add an end-to-end test (or extend `tests/test_end_to_end.py`) for the SBCO fixture.

---

## Phase 2 – Containment Hierarchy Support

### 2-1 Extract level/floor context from RDF
- [x] Parse `sbco:Level` (and `BOT:Storey`) nodes to attach a storey elevation to each contained space.
- [x] Add `StoreySpec` dataclass to `topo2ifc/topology/model.py`.
- [x] Add `extract_storeys()` to `RDFLoader`.
- [x] Add storey vocabulary (`STOREY_CLASSES`, `HAS_SPACE`, `IS_PART_OF_STOREY`, `HAS_STOREY`, `PROP_ELEVATION`, `PROP_LEVEL_NUMBER`, `PROP_STOREY_HEIGHT`) to `vocabulary.py`.
- [x] Store `storey_id` and `storey_elevation` on `SpaceSpec` (new optional fields).
- [x] Add `TestMultiStoreyLoader` tests in `tests/test_rdf.py`.

### 2-2 Multi-storey IFC export
- [x] Extend `IfcExporter` to create one `IfcBuildingStorey` per distinct storey elevation found in the layout.
- [x] Assign each `IfcSpace` to its storey.
- [x] Add `add_storey()` helper to `ifc/ifc_context.py`.
- [x] Create `tests/fixtures/two_storey.ttl` – a two-storey BOT fixture.
- [x] Add `TestMultiStoreyEndToEnd` tests in `tests/test_end_to_end.py`.

---

## Phase 3 – Equipment and Point Pass-through

### 3-1 Extract equipment from SBCO RDF
- [x] Parse `sbco:Equipment` / `sbco:EquipmentExt` nodes and their `sbco:locatedIn` links to spaces.
- [x] Store as a list of `EquipmentSpec` (new dataclass in `topo2ifc/topology/model.py`).

### 3-2 Export equipment as IFC elements
- [x] Map each `EquipmentSpec` to an `IfcBuildingElementProxy` (or appropriate IFC type) placed in its containing space.
- [x] Write `psets.py` property sets for device type and maintenance interval.

### 3-3 Extract and export points
- [x] Parse `sbco:Point` / `sbco:PointExt` nodes linked via `sbco:hasPoint`.
- [x] Represent each point as an `IfcSensor` (or `IfcActuator`) assigned to the parent equipment element.
- [x] Add property sets for `pointType`, `unit`, `hasQuantity`.

---

## Phase 4 – Quality & CI

### 4-1 Improve validation reporting
- [x] Report SBCO constraint violations (e.g., a space missing `sbco:name`) as structured warnings rather than silent defaults.
- [x] Add unit tests for the new warning paths.

### 4-2 Documentation
- [x] Update `README.md` to add an SBCO-vocabulary example and link to the smartbuilding_ontology repository.
- [ ] Add a sample SBCO Turtle file under `sample/sbco_example.ttl` that mirrors the example in the smartbuilding_ontology README.
- [x] Add a step-by-step runtime behavior document under `docs/` and link it from `README.md`.
- [x] Expand runtime documentation with a per-solver explanation (`heuristic` / `ortools`) and solver selection guidance.

### 4-3 CI pipeline
- [x] Add a GitHub Actions workflow (`.github/workflows/ci.yml`) that runs `pytest tests/` on every push and pull request.

## Phase 5 – IFC property enrichment for HVAC integration

### 5-1 Material/thermal metadata on exported building elements
- [ ] Review wall/slab/door IFC output and define required material-related properties for HVAC simulators.
- [ ] Add configurable material/thermal metadata in `Config` and export those as IFC property sets/material assignments.
- [ ] Add end-to-end tests asserting exported IFC contains the new element properties.

---

## Phase 6 – Multi-storey layout algorithm redesign

### 6-1 Formalize floor-wise zoning and vertical-core constraints
- [ ] Define a two-stage solve strategy that preserves current single-storey quality while extending to multi-storey: (1) per-floor 2D solve, (2) vertical core alignment solve.
- [ ] Introduce explicit `VerticalCoreSpec` / `CirculationSpec` requirements in topology extraction for stairs and elevators.
- [ ] Add topology validation rules that enforce stair presence for `storey_count >= 2` and elevator presence for configurable high-rise thresholds.

### 6-2 Implement deterministic stair/elevator placement heuristic
- [ ] Add a pre-placement pass that reserves stair/elevator shafts before room packing and keeps reserved cores aligned across floors.
- [ ] Implement stair adjacency scoring (near corridor, away from dead-end) and elevator centrality scoring (minimize weighted travel distance to floor spaces).
- [ ] Add conflict resolution for multiple cores (e.g., split-core buildings) with fallback to OR-Tools objective penalties.

### 6-3 Extend OR-Tools model for stacked-floor optimization
- [ ] Add decision variables tying core XY positions across storeys (stacking constraints) while keeping existing non-overlap/adjacency constraints per floor.
- [ ] Add objective terms for vertical circulation efficiency (stairs path length, elevator service radius, queue-risk proxy via served area).
- [ ] Keep backward compatibility by gating all new terms behind `SolverConfig.multi_storey_mode` and ensuring single-storey objective behavior is unchanged.

### 6-4 Geometry and IFC integration for vertical circulation
- [ ] Extend geometry generation to create aligned openings/voids for stair and elevator shafts through slabs.
- [ ] Export stairs (`IfcStair`) and elevators (`IfcTransportElement` or proxy fallback) tied to corresponding `IfcBuildingStorey` relations.
- [ ] Add validation ensuring shaft solids and slab openings remain consistent across storeys.

### 6-5 Verification, fixtures, and rollout safety
- [ ] Add fixtures for `2-storey-with-stair`, `6-storey-with-elevator`, and `multi-core-highrise` scenarios.
- [ ] Add regression tests proving existing single-storey layouts are unchanged (golden bbox/similarity checks).
- [ ] Add performance benchmarks and acceptance criteria (solve time, overlap violations, circulation coverage) and document rollout gates.
