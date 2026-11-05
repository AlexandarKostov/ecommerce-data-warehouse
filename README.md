# E-Commerce Data Warehouse

A portfolio Data Engineering project focused on building an end-to-end e-commerce data warehouse using Python, MySQL, and SQL.

The project simulates an e-commerce business, generates synthetic transactional datasets, and establishes the database foundation for an ETL pipeline and analytical reporting.

## 1. Project Overview

The objective is to design and implement a data warehouse that transforms operational e-commerce data into a structured analytical environment.

The project follows a typical Data Engineering workflow:

1. Generate synthetic source datasets.
2. Extract data from CSV files.
3. Validate and transform source records.
4. Load raw records into MySQL staging tables.
5. Populate dimension and fact tables.
6. Build SQL queries for business intelligence and reporting.

**Current development stage:** Database schema and synthetic data generation, with automated validation tests.

## 2. Business Objectives

The warehouse is designed to support business analysis across several areas:

- Customer acquisition and purchasing behavior.
- Product performance and revenue.
- Order volume and fulfillment.
- Payment methods and transaction performance.
- Refunds and returned orders.
- Data quality and ETL pipeline monitoring.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Data generation and ETL development |
| Pandas | Data manipulation |
| Faker | Synthetic data generation |
| MySQL 8.0 | Data warehouse database |
| SQL | Database design and analytics |
| SQLAlchemy | Database connectivity |
| PyMySQL | MySQL driver |
| Pytest | Automated testing |
| Git | Version control |

## 4. Data Warehouse Architecture

The planned architecture separates source data, staging, dimensional modeling, and analytics.

```text
Synthetic Data Generation
          |
          v
      CSV Files
          |
          v
    Data Extraction
          |
          v
   Data Validation
          |
          v
 Data Transformation
          |
          v
    MySQL Staging
          |
          v
 Dimensional Modeling
          |
          +------------------+
          |                  |
          v                  v
     Dimensions           Facts
          |                  |
          +--------+---------+
                   |
                   v
             SQL Analytics
```

The ETL and analytics stages are planned implementation milestones, not yet completed functionality.

## 5. Database Design

The MySQL database is named `ecommerce_dw`.

The initial schema contains 13 tables.

### Staging Tables

These tables are designed to preserve incoming source data before warehouse transformations.

- `stg_customers`
- `stg_products`
- `stg_orders`
- `stg_order_items`
- `stg_payments`

### Dimension Tables

- `dim_customers`
- `dim_products`
- `dim_date`
- `dim_payment_methods`
- `dim_order_statuses`

### Fact Tables

- `fact_sales` — designed around one row per order item.
- `fact_payments` — designed around individual payment transactions.

### ETL Monitoring

- `etl_pipeline_runs` — designed to track ETL execution and processing information.

## 6. Synthetic Data Generation

The project uses Python and Faker to generate realistic synthetic e-commerce datasets.

### Target Dataset Sizes

| Dataset | Target records |
|---|---:|
| Customers | 10,000 |
| Products | 1,000 |
| Orders | 25,000 |
| Order items | Variable |
| Payments | Variable |

The number of order items and payments depends on the generated order scenarios.

### Generated Datasets

- `customers.csv`
- `products.csv`
- `orders.csv`
- `order_items.csv`
- `payments.csv`

### Reproducibility

The generation configuration uses:

- Random seed: `42`
- Reference date: `2026-11-05`

Using a fixed seed makes it possible to reproduce the same synthetic datasets under the same configuration and software environment.

### Payment Scenarios

The payment generator models several business scenarios:

- Pending orders receive pending payments.
- Cancelled orders receive failed payments.
- Returned orders receive completed payments and refunds.
- Other orders receive completed payments, with some failed attempts followed by successful retries.

Payment amounts are calculated using decimal arithmetic to avoid floating-point rounding issues in financial calculations.

## 7. Data Quality Strategy

The project is designed to introduce controlled data-quality issues into source datasets in a later development stage.

The configuration currently defines the following target rates:

| Data quality issue | Target rate |
|---|---:|
| Missing customer email | 2% |
| Duplicate customers | 1% |
| Invalid product price | 1% |
| Missing order date | 0.5% |
| Invalid customer reference | 0.5% |
| Duplicate payments | 1% |

These are configuration targets. The intentional injection and ETL handling of these issues are future implementation tasks.

The objective is to demonstrate validation, error handling, and reliable processing rather than silently discarding invalid records.

## 8. Project Structure

```text
ecommerce-data-warehouse/
│
├── config/
│   └── data_generation.py
│
├── data/
│   ├── raw/
│   └── processed/
│
├── logs/
│
├── sql/
│   └── 01_create_schema.sql
│
├── src/
│   ├── data_generation/
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── extraction/
│   ├── transformation/
│   ├── loading/
│   └── database/
│
├── tests/
│   └── test_data_generation.py
│
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

## 9. Installation and Setup

### Prerequisites

- Python 3.14
- MySQL Server 8.0
- Git

### Clone the repository

```bash
git clone <repository-url>
cd ecommerce-data-warehouse
```

### Create a virtual environment

```bash
python -m venv venv
```

Activate it in Git Bash:

```bash
source venv/Scripts/activate
```

### Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Configure MySQL

Create a database named:

```sql
CREATE DATABASE ecommerce_dw;
```

Execute the schema script:

```text
sql/01_create_schema.sql
```

This creates the initial 13-table database structure.

## 10. Running the Data Generator

The generator is located at:

```text
src/data_generation/generator.py
```

Run it from the project root:

```bash
python -m src.data_generation.generator
```

The current execution block generates a small dataset for development and testing. The configured full dataset sizes will be connected to the main execution workflow in a subsequent development stage.

Generated CSV files are stored in:

```text
data/raw/
```

## 11. Running Automated Tests

The project uses Pytest to validate synthetic data generation and business rules.

Run the complete test suite:

```bash
python -m pytest -v
```

Current tests cover:

- Source ID uniqueness.
- Referential integrity.
- Order and order-item relationships.
- Payment generation rules.
- Required fields.
- Financial calculations.
- Date validation.
- Reproducibility.
- Rejection of invalid payment inputs.

## 12. Development Roadmap

- [x] Initialize project structure.
- [x] Configure Python environment and dependencies.
- [x] Design initial MySQL warehouse schema.
- [x] Implement synthetic customer generation.
- [x] Implement synthetic product generation.
- [x] Implement synthetic order generation.
- [x] Implement order-item generation.
- [x] Implement payment and refund scenarios.
- [x] Add automated data-generation tests.
- [ ] Implement source data extraction.
- [ ] Implement staging table loading.
- [ ] Implement data validation and transformation.
- [ ] Implement dimensional and fact table loading.
- [ ] Introduce controlled data-quality issues.
- [ ] Add ETL execution logging and monitoring.
- [ ] Develop analytical SQL queries and reports.
- [ ] Add integration tests and incremental loading.

## 13. Project Status

This project is being developed incrementally, with an emphasis on data integrity, reproducibility, financial accuracy, relational modeling, and maintainable ETL architecture.