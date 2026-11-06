# E-commerce Data Warehouse

<small>**Status: Work in Progress (WIP)** · **Estimated completion: 75–80%** · Documentation checkpoint: 6 November 2026</small>

> **Project progress:** Approximately 75–80% of the planned project scope is complete. This is an estimated development milestone, not a formal code-coverage or delivery metric. The remaining work is documented in [the development roadmap](docs/ROADMAP.md).

A portfolio Data Engineering project that simulates an e-commerce business and builds a Python- and MySQL-based data warehouse. The project focuses on reproducible source data, reliable ETL processing, data quality, cross-dataset reconciliation, dimensional modeling, and analytical SQL.

> **Current checkpoint:** Synthetic data generation, CSV extraction, MySQL staging, validation, reconciliation, rejected-record persistence, and the Python test suite are implemented. The dimensional and fact loading layer and analytical workloads are still outstanding.

## Project status

| Area | Current status |
|---|---|
| Synthetic source data generation | Implemented and tested |
| Controlled data-quality dataset generation | Implemented and tested |
| CSV extraction | Implemented and tested |
| MySQL connection management | Implemented |
| Staging table loading and ETL audit | Implemented and tested |
| Record-level validation | Implemented and tested |
| Cross-dataset order reconciliation | Implemented and tested |
| Rejected-record persistence | Implemented and tested with mocked/controlled database connections |
| Full MySQL integration of validation pipeline | Pending |
| Dimension and fact loading | Not implemented |
| Analytical SQL and reporting | Not implemented |
| Incremental warehouse loading / SCD Type 2 | Planned |

The current automated test baseline is **277 passing tests** (`pytest -v`, reported 6 November 2026). This is a Python test-suite result; it is not evidence that the complete ETL pipeline has been integration-tested end to end against MySQL.

## Business objectives

The planned warehouse will support analysis of:

- Customer acquisition and purchasing behavior.
- Product performance, revenue, cost, and profit.
- Order volume, status, and fulfillment.
- Payment methods, payment attempts, and refunds.
- Returns and their impact on business performance.
- Data quality and ETL execution reliability.

## Technology stack

| Technology | Purpose |
|---|---|
| Python | Synthetic data generation and ETL implementation |
| Pandas | CSV extraction and tabular data processing |
| Faker | Synthetic source data |
| MySQL 8.0+ | Relational staging and warehouse database |
| SQLAlchemy | Database engine and transactional operations |
| PyMySQL | MySQL DBAPI driver |
| python-dotenv | Environment-based database configuration |
| pytest | Automated tests |
| Git | Version control |

## Architecture

```text
Synthetic data generation
          |
          v
      CSV datasets
          |
          v
     CSV extraction
          |
          v
    MySQL staging
          |
          v
 Record-level validation
          |
          v
 Cross-dataset reconciliation
          |
          +------------------------+
          |                        |
          v                        v
     Accepted records        Rejected records
          |                        |
          |                        v
          |               etl_rejected_records
          |                        |
          +------------+-----------+
                       |
                       v
          Dimension and fact loading
                 (planned)
                       |
                       v
                SQL analytics
                 (planned)
```

The current implemented pipeline ends at validated/reconciled staging data and rejection persistence. Dimension/fact loading and analytics are future milestones.

## Repository structure

```text
.
├── config/
│   └── data_generation.py
├── data/
│   ├── raw/
│   └── quality/
├── docs/
├── sql/
│   ├── 01_create_schema.sql
│   └── 02_create_rejected_records_table.sql
├── src/
│   ├── data_generation/
│   │   ├── generator.py
│   │   ├── quality_dataset_generator.py
│   │   └── quality_injector.py
│   ├── database/
│   │   └── connection.py
│   ├── extraction/
│   │   └── csv_extractor.py
│   ├── loading/
│   │   ├── staging_loader.py
│   │   └── rejected_records_loader.py
│   └── transformation/
│       ├── validation_result.py
│       ├── validation_pipeline.py
│       ├── validation/
│       │   ├── customers.py
│       │   ├── products.py
│       │   ├── orders.py
│       │   ├── order_items.py
│       │   └── payments.py
│       └── reconciliation/
│           └── orders.py
├── tests/
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

The repository also contains a `generator.py.bak` backup file; it is not part of the documented runtime architecture.

## Database

The active MySQL database is **`ecommerce_dw`**. The base schema (`sql/01_create_schema.sql`) creates 13 tables. Migration 02 (`sql/02_create_rejected_records_table.sql`) adds `etl_rejected_records`, bringing the current schema to **14 tables**.

### Staging tables

- `stg_customers`
- `stg_products`
- `stg_orders`
- `stg_order_items`
- `stg_payments`

Incoming source fields are stored as text in staging so validation can inspect raw values before converting them into analytical types. Staging rows are associated with an ETL run through `etl_run_id`.

### Dimension tables

- `dim_customers`
- `dim_products`
- `dim_date`
- `dim_payment_methods`
- `dim_order_statuses`

These tables are defined in the schema. Their ETL loading processes have not yet been implemented.

### Fact tables

- `fact_sales` — designed at one row per order item.
- `fact_payments` — designed at one row per payment transaction.

These tables are defined in the schema. Their ETL loading processes have not yet been implemented.

### ETL control and data quality

- `etl_pipeline_runs` — records pipeline run status and aggregate counters.
- `etl_rejected_records` — stores rejected staging records, their source identifiers, JSON rejection reasons, and raw source payload.

See [Database Schema](docs/DATABASE_SCHEMA.md) for table details.

## Source datasets

The extraction layer expects five CSV files under `data/raw/`:

- `customers.csv`
- `products.csv`
- `orders.csv`
- `order_items.csv`
- `payments.csv`

The synthetic generator uses a fixed seed and configured reference date to support reproducible datasets under the same configuration and software environment. The project also has a separate quality-data workflow under `data/quality/`; those files contain intentionally introduced quality issues and should not be confused with the clean baseline files.

See [ETL Pipeline](docs/ETL_PIPELINE.md) and [Data Validation](docs/DATA_VALIDATION.md).

## Setup

### Prerequisites

- Python version compatible with the pinned project dependencies (the current development environment uses Python 3.14.8).
- MySQL Server 8.0+.
- MySQL Workbench or another MySQL client.
- Git.

### Clone and install

```bash
git clone https://github.com/AlexandarKostov/ecommerce-data-warehouse.git
cd ecommerce-data-warehouse

python -m venv venv
source venv/Scripts/activate       # Git Bash on Windows

python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Configure environment

Copy `.env.example` to `.env` and provide local connection settings. Do not commit `.env` or publish credentials.

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=ecommerce_dw
DB_USERNAME=your_mysql_username
DB_PASSWORD=your_mysql_password
```

The Python connection module loads the project-root `.env` file. The active database name in the current project is `ecommerce_dw`.

### Database initialization

For a fresh database, execute `sql/01_create_schema.sql` in MySQL Workbench. Then execute `sql/02_create_rejected_records_table.sql`.

**Existing development database:** `ecommerce_dw` already has the base schema and rejected-record migration applied. Do not rerun the staging pipeline merely to verify the schema: staging loads append records and create a new ETL run.

## Running the project

### Generate source datasets

```bash
python -m src.data_generation.generator
```

The generator's current execution behavior and configured dataset sizes are described in `config/data_generation.py` and the generator module. Generated CSV files are written under `data/raw/`.

### Run automated tests

```bash
python -m pytest -v
```

Latest reported baseline: **277 passed**.

### ETL entry points

The implementation includes:

- `run_staging_load(...)` in `src/loading/staging_loader.py`.
- `run_validation_pipeline(...)` in `src/transformation/validation_pipeline.py`.
- `run_full_etl_pipeline(...)` in `src/transformation/validation_pipeline.py`.

The full pipeline first creates a staging run in deferred-finalization mode, then validates/reconciles it and finalizes the audit record. These entry points are implemented, but a controlled end-to-end MySQL integration run remains a pending task.

**Operational caution:** `run_staging_load` appends a new run to the configured database. Do not run it against the existing `ecommerce_dw` dataset casually. Plan and verify an intentional integration run before executing it.

## Current database checkpoint

As verified in MySQL Workbench on 6 November 2026:

| Check | Observed result |
|---|---:|
| Database | `ecommerce_dw` |
| Existing baseline ETL run | `run_id = 1` |
| Baseline run status | `SUCCESS` |
| Records extracted | 140,081 |
| Records loaded | 140,081 |
| Records rejected | 0 |
| `etl_rejected_records` row count | 0 |

Run 1 is the original staging baseline. The validation pipeline has not yet been run as a controlled MySQL integration test against this baseline. Preserve run 1 and its staging rows.

## Documentation

- [Project status](docs/PROJECT_STATUS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Database schema](docs/DATABASE_SCHEMA.md)
- [ETL pipeline](docs/ETL_PIPELINE.md)
- [Data validation](docs/DATA_VALIDATION.md)
- [Data reconciliation](docs/DATA_RECONCILIATION.md)
- [Testing](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)

## Project status and contribution approach

This repository is intentionally **WIP**. The current checkpoint documents what has been implemented and tested, and what remains. See `docs/PROJECT_STATUS.md` and `docs/ROADMAP.md` before continuing development.

The project prioritizes data integrity, reproducibility, explicit data-quality handling, financial precision, relational modeling, transaction safety, and maintainable Python code.
