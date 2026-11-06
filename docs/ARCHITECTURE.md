# Architecture

## 1. Purpose

The project is structured as a batch-oriented e-commerce data warehouse pipeline. Synthetic CSV files represent operational source extracts. Python modules extract, validate, reconcile, and load the data into a MySQL staging layer. The warehouse schema also defines dimensions and facts for a later analytical loading phase.

## 2. Current data flow

```text
Synthetic data generator
        |
        +---- clean source files ----> data/raw/
        |
        +---- quality test files ----> data/quality/
                                      |
                                      v
                               CSV extractor
                                      |
                                      v
                           MySQL staging tables
                                      |
                                      v
                            Dataset validators
                                      |
                                      v
                          Cross-dataset reconciliation
                               /             \
                              v               v
                       Valid records    Rejected records
                                             |
                                             v
                                  etl_rejected_records

                       Audit run finalization
```

Dimension and fact loading follows this flow in the intended architecture but has not yet been implemented.

## 3. Main layers

### Source generation

`src/data_generation/` creates synthetic customers, products, orders, order items, and payments. The quality-data modules create controlled data-quality scenarios separately from the clean raw dataset.

### Extraction

`src/extraction/csv_extractor.py` reads the five configured CSV datasets. It preserves source values as strings, validates expected columns, and adds source-file metadata.

### Database connectivity

`src/database/connection.py` loads connection settings from the project-root `.env` file and builds a SQLAlchemy engine using the MySQL PyMySQL driver.

### Staging

`src/loading/staging_loader.py` creates an ETL audit run, extracts source data, validates the extracted dataset structure, and inserts rows into the five staging tables. Inserts are batched and staging data is associated with the run ID.

The loader supports deferred finalization. In that mode it commits staging data and leaves the audit row in `RUNNING`, allowing the validation pipeline to finalize the run later.

### Validation

`src/transformation/validation/` contains independent validators for customers, products, orders, order items, and payments. `validation_result.py` represents accepted records and rejected records with structured issue details.

### Reconciliation

`src/transformation/reconciliation/orders.py` checks relationships across orders, order items, and payments. It ensures that accepted parent/child records are consistent and that payment scenarios align with order statuses and calculated order totals.

### Rejected-record persistence

`src/loading/rejected_records_loader.py` persists rejected staging records to `etl_rejected_records`. Each rejected physical staging record is stored once, with multiple validation/reconciliation reasons represented in JSON.

### Validation orchestration

`src/transformation/validation_pipeline.py` loads the staging datasets for a specific run, verifies basic staging completeness, runs validators and reconciliation, persists rejected records, and finalizes the audit run. Rejection persistence and successful audit finalization share a database transaction.

## 4. Database layers

- **Control:** `etl_pipeline_runs`
- **Staging:** `stg_customers`, `stg_products`, `stg_orders`, `stg_order_items`, `stg_payments`
- **Dimensions:** `dim_customers`, `dim_products`, `dim_date`, `dim_payment_methods`, `dim_order_statuses`
- **Facts:** `fact_sales`, `fact_payments`
- **Data quality:** `etl_rejected_records`

The dimension and fact tables are currently schema definitions, not populated outputs of an implemented warehouse loader.

## 5. Key design decisions

- Preserve source values in staging as text so malformed values can be examined rather than coerced during extraction.
- Keep validation functions separate from database writes so business rules can be unit-tested.
- Use structured rejection codes, field names, and messages instead of a single opaque error string.
- Keep cross-dataset reconciliation separate from individual dataset validation.
- Use `Decimal` for financial calculations to avoid binary floating-point errors.
- Track physical rejected records separately from the number of rejection issues. One record may have multiple issues.
- Scope staging reads to a specific `etl_run_id`.
- Keep staging loading and validation finalization as separate stages, with conditional audit status updates.
- Keep sales and payment facts separate to avoid fan-out when analyzing multiple payment transactions per order item/order.

## 6. Current limitations

- No dimension/fact loader exists yet.
- No scheduled orchestrator or workflow scheduler is configured.
- No SCD Type 2 implementation exists yet.
- Full MySQL integration behavior for the new validation pipeline remains to be verified with a controlled run.
- Staging loading appends new rows; rerunning against the production-like development database must be intentional and audited.
