# Database Schema

## 1. Database and migration state

Active database: **`ecommerce_dw`**  
Database engine: MySQL 8.0+  
Base schema: `sql/01_create_schema.sql`  
Additional migration: `sql/02_create_rejected_records_table.sql`

The base schema creates 13 tables. Migration 02 adds one table, `etl_rejected_records`. The current expected schema therefore contains **14 tables**.

The migration has been applied to `ecommerce_dw`; the rejected-record table was verified to contain zero rows at the checkpoint.

## 2. Table inventory

| Layer | Table | Purpose |
|---|---|---|
| Control | `etl_pipeline_runs` | One audit record per ETL execution |
| Staging | `stg_customers` | Raw customer source records |
| Staging | `stg_products` | Raw product source records |
| Staging | `stg_orders` | Raw order source records |
| Staging | `stg_order_items` | Raw order-item source records |
| Staging | `stg_payments` | Raw payment source records |
| Dimension | `dim_customers` | Customer analytical attributes |
| Dimension | `dim_products` | Product analytical attributes |
| Dimension | `dim_date` | Calendar attributes |
| Dimension | `dim_payment_methods` | Payment method lookup |
| Dimension | `dim_order_statuses` | Order status lookup |
| Fact | `fact_sales` | Sales measures at order-item grain |
| Fact | `fact_payments` | Payment transaction measures |
| Data quality | `etl_rejected_records` | Rejected staging records and reasons |

## 3. ETL audit table

`etl_pipeline_runs` stores:

- `run_id`: generated primary key.
- `pipeline_name`: pipeline identifier.
- `started_at` and `finished_at`: execution timestamps.
- `status`: `RUNNING`, `SUCCESS`, or `FAILED`.
- `records_extracted`, `records_loaded`, `records_rejected`: aggregate physical-record counters.
- `error_message`: failure information.
- `created_at`: audit-row creation timestamp.

`records_rejected` represents rejected physical records, not the number of individual rejection issues.

## 4. Staging design

Each staging table has:

- `staging_id`: table-specific surrogate primary key.
- `etl_run_id`: reference to `etl_pipeline_runs.run_id`.
- Source-system identifier and raw source attributes.
- `source_file`: source file metadata.
- `loaded_at`: database load timestamp.

Source business fields are stored as `VARCHAR` to preserve raw input for validation. The staging tables are append-oriented and associated with a particular ETL run.

## 5. Dimension design

### `dim_customers`

Primary key: `customer_key`  
Business/source key: unique `source_customer_id`

Contains customer name, contact information, geography, and registration date.

### `dim_products`

Primary key: `product_key`  
Business/source key: unique `source_product_id`

Contains product name, category, price, and cost.

### `dim_date`

Primary key: `date_key`  
Unique attribute: `full_date`

Contains day, week, month, quarter, and year attributes. The date-key generation and population process remains to be implemented.

### `dim_payment_methods`

Primary key: `payment_method_key`  
Unique attribute: `method_name`

### `dim_order_statuses`

Primary key: `order_status_key`  
Unique attribute: `status_name`

The base schema seeds six order statuses and five payment methods.

## 6. Fact design and grain

### `fact_sales`

**Declared grain: one row per source order item.**

The table references customer, product, date, and order-status dimensions. Measures include quantity, unit price, discount, gross revenue, net revenue, total cost, and profit.

The unique constraint on `source_order_item_id` supports one fact row per source order item.

### `fact_payments`

**Declared grain: one row per source payment transaction.**

The table references payment method and payment date dimensions and stores payment status and amount. The unique constraint on `source_payment_id` prevents duplicate source payment identifiers.

Keeping payments separate from sales avoids multiplying sales measures when an order has multiple payment attempts or refund transactions.

## 7. Rejected records

`etl_rejected_records` contains:

- `rejection_id`: primary key.
- `etl_run_id`: foreign key to the ETL audit table.
- `source_table`: one of the supported staging table names.
- `staging_record_id`: original staging row identifier.
- `source_record_id`: source-system identifier, when available.
- `rejection_reasons`: JSON array of structured issues.
- `raw_record`: JSON representation of the source staging record.
- `rejected_at`: persistence timestamp.

A unique constraint on `(etl_run_id, source_table, staging_record_id)` ensures that a physical staging record is persisted at most once per run. `staging_record_id` intentionally has no direct foreign key because it can refer to any one of the five staging tables.

## 8. Relationship overview

```text
etl_pipeline_runs
   |----< stg_customers
   |----< stg_products
   |----< stg_orders
   |----< stg_order_items
   |----< stg_payments
   |----< etl_rejected_records

dim_customers --------< fact_sales
dim_products ---------< fact_sales
dim_date -------------< fact_sales
dim_order_statuses ---< fact_sales

dim_payment_methods --< fact_payments
dim_date -------------< fact_payments
```

The diagram shows declared database relationships. Business relationships between staging datasets are validated in Python; they are not all enforced by staging-table foreign keys.

## 9. Future schema work

- Define and implement the date dimension population range and key convention.
- Decide whether dimensions require Type 1, Type 2, or mixed change handling.
- Define fact-table handling for late-arriving dimensions and corrected source records.
- Define a durable incremental-load watermark or source-change strategy.
- Review whether audit counters should eventually include per-dataset counts.
