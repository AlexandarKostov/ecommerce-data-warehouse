# Development Roadmap

**Current status:** Work in Progress (WIP)  
**Checkpoint:** 6 November 2026

This roadmap records the remaining work in implementation order. A task is not considered complete merely because its table or module exists; its behavior must be implemented and tested.

## Phase 1 — Verify the implemented ETL foundation

- [ ] Design small, deterministic CSV fixtures for all five source datasets.
- [ ] Review how the fixture will be isolated within the existing `ecommerce_dw` database.
- [ ] Preserve existing baseline run 1 and its 140,081 staging rows.
- [ ] Execute a controlled staging load.
- [ ] Execute validation and cross-dataset reconciliation for that run.
- [ ] Verify valid/rejected record counts and persisted JSON payloads.
- [ ] Verify `etl_pipeline_runs` counters and final status.
- [ ] Exercise failure and transaction rollback behavior against MySQL.
- [ ] Document the integration results.

**Exit criteria:** A controlled MySQL run demonstrates the implemented staging → validation → reconciliation → rejected persistence → audit finalization workflow without modifying the baseline run.

## Phase 2 — Implement dimension loading

- [ ] Define dimension load contracts and source-to-target mappings.
- [ ] Load `dim_customers`.
- [ ] Load `dim_products`.
- [ ] Define the date range and key convention for `dim_date`.
- [ ] Populate `dim_date`.
- [ ] Load/verify `dim_payment_methods`.
- [ ] Load/verify `dim_order_statuses`.
- [ ] Add tests for inserts, updates, duplicates, and referential integrity.

**Exit criteria:** Validated source entities can be loaded into dimensions with deterministic keys and tested behavior.

## Phase 3 — Implement fact loading

- [ ] Define the exact sales fact grain and source-to-dimension key lookups.
- [ ] Load `fact_sales` at one row per order item.
- [ ] Calculate gross revenue, net revenue, cost, and profit consistently.
- [ ] Load `fact_payments` at one row per payment transaction.
- [ ] Handle payment attempts and refunds without multiplying sales measures.
- [ ] Add tests for missing dimension keys, duplicates, financial calculations, and fact grain.

**Exit criteria:** Facts load with correct measures, surrogate keys, and referential integrity.

## Phase 4 — Complete orchestration and operational behavior

- [ ] Integrate staging, validation, reconciliation, dimension loading, and fact loading into a single controlled workflow.
- [ ] Define rerun and idempotency behavior.
- [ ] Implement incremental processing and a reliable change/watermark strategy.
- [ ] Define recovery behavior for partially completed runs.
- [ ] Improve per-dataset audit metrics where useful.
- [ ] Add structured logging and operational error reporting.
- [ ] Add end-to-end integration tests.

**Exit criteria:** A rerunnable, observable ETL workflow processes new source data without duplicate or inconsistent warehouse records.

## Phase 5 — Historical dimension handling

- [ ] Identify dimensions requiring historical tracking.
- [ ] Define SCD Type 2 attributes and effective-date semantics.
- [ ] Add surrogate versioning and current-row indicators where needed.
- [ ] Handle fact assignment to the correct historical dimension version.
- [ ] Test changed, unchanged, and late-arriving dimension records.

**Exit criteria:** Historical attribute changes are represented correctly and facts retain the intended historical context.

## Phase 6 — Analytics and business KPIs

- [ ] Revenue and profit trends.
- [ ] Customer acquisition and repeat-purchase analysis.
- [ ] Customer lifetime value (with a documented definition).
- [ ] Product/category performance.
- [ ] Order status and fulfillment analysis.
- [ ] Payment-method and payment-failure analysis.
- [ ] Refund and return analysis.
- [ ] Monthly and quarterly reporting.
- [ ] Validate analytical results against controlled source examples.

**Exit criteria:** SQL queries answer documented business questions and reconcile to warehouse facts.

## Phase 7 — Performance, documentation, and portfolio delivery

- [ ] Review indexes and query plans for representative analytical queries.
- [ ] Benchmark larger loads and analytical queries.
- [ ] Document setup, architecture, schema, ETL, validation, reconciliation, and testing.
- [ ] Add an architecture diagram and selected data-flow examples.
- [ ] Add representative SQL queries and result examples.
- [ ] Review README accuracy and reproducibility.
- [ ] Review Git history and commit all intended implementation changes.
- [ ] Prepare a concise portfolio walkthrough.

**Exit criteria:** Another developer can set up the project, understand its architecture, run its tests, and evaluate its data engineering capabilities.

## Resume instructions

1. Read `README.md` and `PROJECT_STATUS.md`.
2. Check `git status --short` before changing anything.
3. Activate the project virtual environment.
4. Run `python -m pytest -v` to establish a fresh test baseline.
5. Inspect the current database state in MySQL Workbench.
6. Start with Phase 1 and preserve baseline run 1.
