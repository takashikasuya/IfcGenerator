# AGENTS.md

## 1. Repository Overview

- **Purpose**: Convert RDF building topology into IFC4 models via the pipeline **RDF topology → Layout solver → Parametric geometry → IFC**.
- **Data flow**: An input Turtle / JSON-LD file is parsed by `topo2ifc/rdf/loader.py` using the vocabulary in `topo2ifc/rdf/vocabulary.py`; spaces, adjacencies, and connections are assembled into a `TopologyGraph`; the layout solver produces axis-aligned rectangles; geometry helpers (`walls`, `slabs`, `doors`) build 3-D shapes; and `topo2ifc/ifc/exporter.py` writes an IFC4 file with `ifcopenshell`.
- **Building topology RDF**: Input RDF **must** follow the Smart Building Co-creation Organization (SBCO) ontology defined at <https://github.com/takashikasuya/smartbuiding_ontology>. The canonical prefix is `sbco: <https://www.sbco.or.jp/ont/>` and the cardinal hierarchy is `Site → Building → Level → Space → Equipment → Point`. The vocabulary module (`topo2ifc/rdf/vocabulary.py`) must recognise SBCO class and property URIs in addition to BOT and Brick terms.
- **Package layout**:
  - `topo2ifc/cli.py` – Click CLI entry point
  - `topo2ifc/config.py` – `Config`, `GeometryConfig`, `SolverConfig` dataclasses
  - `topo2ifc/rdf/` – RDF loading and vocabulary mapping
  - `topo2ifc/topology/` – `SpaceSpec`, `TopologyGraph`
  - `topo2ifc/layout/` – heuristic and OR-Tools layout solvers
  - `topo2ifc/geometry/` – wall / slab / door extraction
  - `topo2ifc/ifc/` – IFC4 export (`ifcopenshell`)
  - `topo2ifc/validate/` – topology and layout validation, constraint reports
  - `tests/` – pytest test suite; fixtures live under `tests/fixtures/`

## 2. Development Workflow

- **Follow PLANS.md**: Before starting work, read `PLANS.md`. Execute tasks in the order listed. After completing each task, mark it as done (`- [x]`) and commit.
- **Plan-first**: If `PLANS.md` does not yet exist or a task is not listed, add it before implementing.
- **Incremental commits**: Commit after each completed task so progress is traceable.
- **Tests first**: Write or update `tests/` before or alongside implementation. Run `pytest tests/` after every change.
- **Minimal changes**: Modify only the files required to accomplish the task; avoid unrelated refactoring.

## 3. Operating Principles

- **SBCO vocabulary priority**: When reading RDF topology, recognise SBCO terms (`sbco:Space`, `sbco:hasPart`, `sbco:name`, `sbco:Equipment`, `sbco:Point`, etc.) as first-class citizens alongside BOT and Brick. Add new SBCO URI tuples to `topo2ifc/rdf/vocabulary.py` rather than hard-coding them elsewhere.
- **Single source of vocabulary**: All RDF namespace declarations live in `topo2ifc/rdf/vocabulary.py`. Do not scatter namespace strings across other modules.
- **Configuration over code**: Geometric defaults (wall height, slab thickness, etc.) belong in `Config` / YAML; never hard-code them in geometry helpers.
- **Solver abstraction**: Layout solvers implement a common interface (`solve(topo) -> list[LayoutRect]`). Do not call solver internals from outside `topo2ifc/layout/`.
- **No side effects in library code**: `cli.py` owns all I/O (file reads/writes, logging setup, `sys.exit`). Library modules must not call `sys.exit` or configure logging.

## 4. Safety & Security Guardrails

- **No secrets**: Do not add `.env` files, API keys, or credentials to the repository.
- **Validate inputs early**: `validate_topology()` must be called before the layout solver; `validate_layout()` must be called before geometry generation. Do not suppress or skip validation steps.
- **No arbitrary code execution**: Do not use `eval` or `exec` on external data (e.g., RDF literal values).
- **Dependency pinning**: When adding a new package, add it to `pyproject.toml` with a minimum version bound and check the GitHub Advisory Database for known vulnerabilities.

## 5. Tooling & Commands

- **Install**: `pip install -e .` (add `[ortools]` for the OR-Tools solver)
- **Run**: `topo2ifc --input topology.ttl --output out.ifc [--solver ortools] [--seed 42] [--debug /tmp/debug/]`
- **Test**: `pytest tests/`
- **Lint** (if configured): `ruff check topo2ifc tests` (or the linter already present in the repo)
- **SBCO sample**: A minimal SBCO-vocabulary Turtle fixture lives at `tests/fixtures/sbco_minimal.ttl`; use it to verify SBCO support without a full building model.

## 6. Change Workflow

1. Read `PLANS.md` and identify the next incomplete task.
2. Understand the relevant code paths before editing (use `grep`/`glob`/file reads).
3. Write or update tests in `tests/` that will fail before the fix and pass after.
4. Implement the change in the smallest set of files possible.
5. Run `pytest tests/` and confirm all tests pass.
6. Mark the task done in `PLANS.md` and commit.

## 7. MUST NOT List

- MUST NOT skip reading `PLANS.md` before starting implementation work.
- MUST NOT add SBCO or other namespace strings directly into loader or solver code—they belong in `topo2ifc/rdf/vocabulary.py`.
- MUST NOT call `sys.exit`, `print`, or configure `logging` from inside library modules (only `cli.py` does this).
- MUST NOT commit broken tests; always run `pytest tests/` before committing.
- MUST NOT hard-code geometric constants (wall height, thickness, etc.) outside `config.py`.
- MUST NOT edit generated or derived files by hand if they can be regenerated from source.
