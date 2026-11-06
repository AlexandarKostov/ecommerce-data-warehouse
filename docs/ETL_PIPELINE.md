# ETL Pipeline

## 1. Current scope

The implemented ETL foundation covers CSV extraction, staging, validation, cross-dataset reconciliation, rejected-record persistence, and audit finalization. Dimension and fact loading is not yet implemented.

## 2. Source datasets

The extractor expects five datasets, keyed internally by staging table name:

| Staging table | CSV file |
|---|---|
| `stg_customers` | `customers.csv` |
| `stg_products` | `products.csv` |
| `stg_orders` | `orders.csv` |
| `stg_order_items` | `order_items.csv` |
| `stg_payments` | `payments.csv` |

The expected column lists are defined in `src/extraction/csv_extractor.py`.

## 3. Extraction

Module: `src/extraction/csv_extractor.py`

The extractor:

- Reads the configured five CSV files.
- Reads source values as strings.
- Uses UTF-8 encoding.
- Preserves empty strings and literal values such as `NA` rather than automatically converting them to nulls.
- Rejects missing files, empty datasets, malformed rows, and unexpected/missing columns.
- Reorders columns to the configured schema.
- Adds `source_file` metadata.
- Returns a mapping of staging table names to Pandas DataFrames.

## 4. Staging load

Module: `src/loading/staging_loader.py`

The staging loader:

1. Creates an ETL audit record in `RUNNING` state.
2. Extracts the source datasets.
3. Validates the dataset mapping and expected DataFrame columns.
4. Counts extracted records.
5. Inserts records into the five staging tables in batches.
6. Either finalizes the run as `SUCCESS` or leaves it `RUNNING` for validation, depending on `finalize_run`.
7. On an exception, rolls back the staging transaction and records the run as `FAILED`.

`run_staging_load(engine, data_directory=None, finalize_run=True)` supports two modes:

- `finalize_run=True`: staging load is finalized as `SUCCESS`.
- `finalize_run=False`: staging load records progress but leaves the audit row `RUNNING` for the validation pipeline.

The current validation orchestration uses deferred finalization.

## 5. Validation and reconciliation orchestration

Module: `src/transformation/validation_pipeline.py`

`run_validation_pipeline(engine, run_id)`:

1. Validates the run ID argument.
2. Retrieves the audit record and requires the run to be `RUNNING`.
3. Loads the five staging datasets filtered by `etl_run_id`.
4. Checks aggregate staging completeness against audit counts.
5. Runs dataset-level validation.
6. Calculates expected order totals using decimal arithmetic.
7. Runs cross-dataset order reconciliation.
8. Builds rejected datasets for all five staging tables.
9. Persists rejected records.
10. Updates audit counters and marks the run `SUCCESS` in the same transaction as rejected-record persistence.

If validation/finalization fails, the rejection persistence transaction is rolled back and the run is conditionally marked `FAILED`.

`run_full_etl_pipeline(engine, data_directory=None)` combines deferred staging loading and validation orchestration.

## 6. Transaction boundaries

- The staging loader creates the audit row and commits staging data in its staging transaction.
- Deferred mode leaves the audit record in `RUNNING`.
- Rejected-record persistence does not commit or roll back; the caller owns the transaction.
- Rejected-record replacement and successful audit finalization are performed in one transaction.
- Failure marking uses a separate transaction after the failed operation has rolled back.
- Conditional status updates prevent an already-finalized run from being changed back to `FAILED`.

## 7. Audit and rejection semantics

- `records_extracted`: physical source rows extracted across configured datasets.
- `records_loaded`: physical staging rows loaded.
- `records_rejected`: physical staging records rejected by validation/reconciliation.
- `issue_count`: number of validation/reconciliation reasons; this can be greater than `records_rejected`.

A single rejected source record can have multiple reasons, but it is stored once in `etl_rejected_records`.

## 8. Operational cautions

- Staging loads append records; they do not replace the existing baseline.
- Each staging execution creates a new audit run.
- Always scope downstream reads by `etl_run_id`.
- Do not rerun the pipeline against `ecommerce_dw` without intentionally planning the additional run and reviewing the source directory.
- The existing run 1 is the baseline and should be preserved.
- The full pipeline has not yet been verified through a controlled MySQL integration run.

## 9. Next ETL milestones

1. Design a small deterministic integration fixture for all five CSV datasets.
2. Execute a controlled run in the active database only after reviewing the append and cleanup implications.
3. Verify both accepted and rejected records, audit counters, transaction rollback, and failure states.
4. Implement dimension loading.
5. Implement fact loading.
6. Add idempotency and incremental processing.
