# PLANS.md

Development plan for the IfcGenerator (`topo2ifc`) project.
AI agents must read this file before starting work and mark each task `[x]` when complete.

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
- [ ] Map each `EquipmentSpec` to an `IfcBuildingElementProxy` (or appropriate IFC type) placed in its containing space.
- [ ] Write `psets.py` property sets for device type and maintenance interval.

### 3-3 Extract and export points
- [ ] Parse `sbco:Point` / `sbco:PointExt` nodes linked via `sbco:hasPoint`.
- [ ] Represent each point as an `IfcSensor` (or `IfcActuator`) assigned to the parent equipment element.
- [ ] Add property sets for `pointType`, `unit`, `hasQuantity`.

---

## Phase 4 – Quality & CI

### 4-1 Improve validation reporting
- [ ] Report SBCO constraint violations (e.g., a space missing `sbco:name`) as structured warnings rather than silent defaults.
- [ ] Add unit tests for the new warning paths.

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
