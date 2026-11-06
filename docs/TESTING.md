# Testing

## 1. Current test baseline

The latest reported full test run on 6 November 2026:

```text
277 passed in 4.89s
```

Environment reported by pytest:

- Windows
- Python 3.14.8
- pytest 9.2.0

This is the current reported baseline. Re-run the suite when resuming work to confirm the current working tree still passes.

## 2. Run the suite

Activate the project virtual environment, then run:

```bash
python -m pytest -v
```

For a focused module:

```bash
python -m pytest -v tests/test_validation_pipeline.py
python -m pytest -v tests/test_rejected_records_loader.py
python -m pytest -v tests/test_staging_loader.py
```

Compile the main pipeline modules:

```bash
python -m py_compile \
    src/loading/staging_loader.py \
    src/loading/rejected_records_loader.py \
    src/transformation/validation_pipeline.py
```

Check whitespace and patch formatting:

```bash
git diff --check
```

## 3. Test coverage areas

The test suite includes:

- Synthetic data generation and reproducibility.
- Quality dataset generation and injection.
- CSV extraction behavior and schema checks.
- Customer, product, order, order-item, and payment validation.
- Validation result construction and issue handling.
- Cross-dataset order reconciliation.
- Staging loader behavior, including deferred finalization.
- Rejected-record loader mapping, JSON serialization, validation, and transaction ownership.
- Validation pipeline orchestration, audit state handling, and failure paths.

## 4. Unit tests versus integration tests

Passing unit tests do not establish that the complete pipeline works against the actual MySQL database.

The following integration checks remain pending:

1. A controlled staging load with a small fixture.
2. Validation of the run's staging rows from MySQL.
3. Persistence of rejected records into `etl_rejected_records`.
4. Correct audit counters and final `SUCCESS` status.
5. Failure path and rollback behavior.
6. Protection against re-finalizing an already completed run.

## 5. Database safety

The active database is `ecommerce_dw`. Existing baseline run 1 loaded 140,081 staging records and is `SUCCESS`.

Do not use run 1 as a test fixture. Do not casually rerun the full raw dataset: the staging loader appends a new run. Design and review a controlled fixture and cleanup strategy before integration testing.
