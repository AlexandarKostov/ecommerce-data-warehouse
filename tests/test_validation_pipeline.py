
"""Tests for the end-to-end validation pipeline."""

import json

import pytest
from sqlalchemy import create_engine, text

from src.extraction.csv_extractor import SOURCE_DATASETS
from src.transformation.validation_pipeline import (
    run_validation_pipeline,
    ValidationPipelineError,
)


@pytest.fixture
def pipeline_engine():
    """Create an isolated SQLite warehouse for pipeline tests."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:

        connection.execute(
            text(
                """
                CREATE TABLE etl_pipeline_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_name VARCHAR(100) NOT NULL,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
                    records_extracted BIGINT NOT NULL DEFAULT 0,
                    records_loaded BIGINT NOT NULL DEFAULT 0,
                    records_rejected BIGINT NOT NULL DEFAULT 0,
                    error_message TEXT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE TABLE etl_rejected_records (
                    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    etl_run_id BIGINT NOT NULL,
                    source_table VARCHAR(100) NOT NULL,
                    staging_record_id BIGINT NOT NULL,
                    source_record_id VARCHAR(100),
                    rejection_reasons JSON NOT NULL,
                    raw_record JSON NOT NULL,
                    UNIQUE (etl_run_id, source_table, staging_record_id)
                )
                """
            )
        )

        for staging_table, configuration in SOURCE_DATASETS.items():

            columns = configuration["columns"] + ["source_file"]

            definitions = [
                "`staging_id` INTEGER PRIMARY KEY AUTOINCREMENT",
                "`etl_run_id` BIGINT NOT NULL",
            ]

            definitions.extend(
                f"`{column}` VARCHAR(255)"
                for column in columns
            )

            definitions.append(
                "`loaded_at` DATETIME DEFAULT CURRENT_TIMESTAMP"
            )

            connection.execute(
                text(
                    f"""
                    CREATE TABLE `{staging_table}` (
                        {", ".join(definitions)}
                    )
                    """
                )
            )

        connection.execute(
            text(
                """
                INSERT INTO etl_pipeline_runs (
                    pipeline_name,
                    status,
                    records_extracted,
                    records_loaded
                )
                VALUES (
                    'ecommerce_data_warehouse',
                    'RUNNING',
                    9,
                    9
                )
                """
            )
        )

        # One valid customer and one invalid customer.
        connection.execute(
            text(
                """
                INSERT INTO stg_customers (
                    etl_run_id,
                    source_customer_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    country,
                    city,
                    registration_date,
                    source_file
                )
                VALUES
                (
                    1, 'C1', 'Alex', 'Smith',
                    'alex@example.com', '070000001',
                    'North Macedonia', 'Skopje',
                    '2025-01-01', 'customers.csv'
                ),
                (
                    1, 'C2', 'John', 'Doe',
                    '', '070000002',
                    'North Macedonia', 'Shtip',
                    '2025-01-02', 'customers.csv'
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO stg_products (
                    etl_run_id,
                    source_product_id,
                    product_name,
                    category,
                    unit_price,
                    unit_cost,
                    stock_quantity,
                    created_at_source,
                    source_file
                )
                VALUES (
                    1, 'P1', 'Test Product', 'Electronics',
                    '10.00', '5.00', '100',
                    '2025-01-01', 'products.csv'
                )
                """
            )
        )

        # O1 references the valid customer.
        # O2 references the invalid customer.
        connection.execute(
            text(
                """
                INSERT INTO stg_orders (
                    etl_run_id,
                    source_order_id,
                    source_customer_id,
                    order_date,
                    order_status,
                    shipping_country,
                    shipping_city,
                    source_file
                )
                VALUES
                (
                    1, 'O1', 'C1', '2026-11-01',
                    'delivered', 'North Macedonia',
                    'Skopje', 'orders.csv'
                ),
                (
                    1, 'O2', 'C2', '2026-11-01',
                    'delivered', 'North Macedonia',
                    'Shtip', 'orders.csv'
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO stg_order_items (
                    etl_run_id,
                    source_order_item_id,
                    source_order_id,
                    source_product_id,
                    quantity,
                    unit_price,
                    discount_amount,
                    source_file
                )
                VALUES
                (
                    1, 'I1', 'O1', 'P1',
                    '2', '10.00', '0.00', 'order_items.csv'
                ),
                (
                    1, 'I2', 'O2', 'P1',
                    '2', '10.00', '0.00', 'order_items.csv'
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO stg_payments (
                    etl_run_id,
                    source_payment_id,
                    source_order_id,
                    payment_method,
                    payment_status,
                    payment_date,
                    payment_amount,
                    source_file
                )
                VALUES
                (
                    1, 'PAY1', 'O1', 'Credit Card',
                    'Completed', '2026-11-02',
                    '20.00', 'payments.csv'
                ),
                (
                    1, 'PAY2', 'O2', 'Credit Card',
                    'Completed', '2026-11-02',
                    '20.00', 'payments.csv'
                )
                """
            )
        )

    yield engine
    engine.dispose()


def test_validation_pipeline_reconciles_and_persists_rejections(
    pipeline_engine,
):
    """Valid records survive and invalid dependent records are rejected."""

    result = run_validation_pipeline(
        pipeline_engine,
        run_id=1,
    )

    assert result["status"] == "SUCCESS"
    assert result["records_extracted"] == 9
    assert result["records_loaded"] == 9
    assert result["records_rejected"] == 4

    assert result["valid_by_table"] == {
        "stg_customers": 1,
        "stg_products": 1,
        "stg_orders": 1,
        "stg_order_items": 1,
        "stg_payments": 1,
    }

    assert result["rejected_by_table"] == {
        "stg_customers": 1,
        "stg_products": 0,
        "stg_orders": 1,
        "stg_order_items": 1,
        "stg_payments": 1,
    }

    with pipeline_engine.connect() as connection:

        audit = connection.execute(
            text(
                """
                SELECT status, records_rejected, error_message
                FROM etl_pipeline_runs
                WHERE run_id = 1
                """
            )
        ).mappings().one()

        rejected_rows = connection.execute(
            text(
                """
                SELECT
                    source_table,
                    staging_record_id,
                    source_record_id,
                    rejection_reasons,
                    raw_record
                FROM etl_rejected_records
                WHERE etl_run_id = 1
                ORDER BY source_table
                """
            )
        ).mappings().all()

    assert audit["status"] == "SUCCESS"
    assert audit["records_rejected"] == 4
    assert audit["error_message"] is None

    assert len(rejected_rows) == 4

    rejected_by_table = {
        row["source_table"]: row
        for row in rejected_rows
    }

    assert rejected_by_table["stg_customers"]["source_record_id"] == "C2"
    assert rejected_by_table["stg_orders"]["source_record_id"] == "O2"
    assert rejected_by_table["stg_order_items"]["source_record_id"] == "I2"
    assert rejected_by_table["stg_payments"]["source_record_id"] == "PAY2"

    customer_reasons = json.loads(
        rejected_by_table["stg_customers"]["rejection_reasons"]
    )

    assert any(
        reason["code"] == "MISSING_EMAIL"
        for reason in customer_reasons
    )

    order_item_reasons = json.loads(
        rejected_by_table["stg_order_items"]["rejection_reasons"]
    )

    assert any(
        reason["code"] == "invalid_order_reference"
        for reason in order_item_reasons
    )

    # Raw source data must remain available for investigation.
    raw_customer = json.loads(
        rejected_by_table["stg_customers"]["raw_record"]
    )

    assert raw_customer["source_customer_id"] == "C2"
    assert raw_customer["email"] == ""


def test_validation_failure_rolls_back_rejected_records(
    pipeline_engine,
):
    """A persistence failure must not leave partial rejection rows."""

    with pipeline_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER fail_rejected_insert
                BEFORE INSERT ON etl_rejected_records
                BEGIN
                    SELECT RAISE(ABORT, 'simulated persistence failure');
                END;
                """
            )
        )

    with pytest.raises(
        ValidationPipelineError,
        match="simulated persistence failure",
    ):
        run_validation_pipeline(
            pipeline_engine,
            run_id=1,
        )

    with pipeline_engine.connect() as connection:

        audit = connection.execute(
            text(
                """
                SELECT status, records_rejected, error_message
                FROM etl_pipeline_runs
                WHERE run_id = 1
                """
            )
        ).mappings().one()

        rejected_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM etl_rejected_records
                WHERE etl_run_id = 1
                """
            )
        ).scalar_one()

    assert audit["status"] == "FAILED"
    assert audit["records_rejected"] == 0
    assert "simulated persistence failure" in audit["error_message"]

    assert rejected_count == 0


def test_validation_rejects_unknown_run_id(pipeline_engine):
    """A nonexistent ETL run must not be validated."""

    with pytest.raises(
        ValidationPipelineError,
        match="does not exist",
    ):
        run_validation_pipeline(
            pipeline_engine,
            run_id=999,
        )

def test_validation_rejects_already_successful_run_without_modifying_it(
    pipeline_engine,
):
    """A finalized successful run cannot be revalidated or downgraded."""

    with pipeline_engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE etl_pipeline_runs
                SET status = 'SUCCESS'
                WHERE run_id = 1
                """
            )
        )

    with pytest.raises(
        ValidationPipelineError,
        match="already been finalized",
    ):
        run_validation_pipeline(
            pipeline_engine,
            run_id=1,
        )

    with pipeline_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT status, records_rejected, error_message
                FROM etl_pipeline_runs
                WHERE run_id = 1
                """
            )
        ).mappings().one()

        rejected_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM etl_rejected_records
                WHERE etl_run_id = 1
                """
            )
        ).scalar_one()

    assert audit["status"] == "SUCCESS"
    assert audit["records_rejected"] == 0
    assert audit["error_message"] is None
    assert rejected_count == 0


def test_validation_fails_when_staging_records_are_missing(
    pipeline_engine,
):
    """Missing staging rows must prevent successful validation."""

    with pipeline_engine.begin() as connection:
        connection.execute(
            text(
                """
                DELETE FROM stg_products
                WHERE etl_run_id = 1
                """
            )
        )

    with pytest.raises(
        ValidationPipelineError,
        match="Staging datasets are unexpectedly empty",
    ):
        run_validation_pipeline(
            pipeline_engine,
            run_id=1,
        )

    with pipeline_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT status, records_loaded, records_rejected
                FROM etl_pipeline_runs
                WHERE run_id = 1
                """
            )
        ).mappings().one()

        rejected_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM etl_rejected_records
                WHERE etl_run_id = 1
                """
            )
        ).scalar_one()

    assert audit["status"] == "FAILED"
    assert audit["records_loaded"] == 9
    assert audit["records_rejected"] == 0
    assert rejected_count == 0


def test_validation_fails_when_audit_counters_are_inconsistent(
    pipeline_engine,
):
    """Extracted and loaded audit counters must agree."""

    with pipeline_engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE etl_pipeline_runs
                SET records_loaded = 8
                WHERE run_id = 1
                """
            )
        )

    with pytest.raises(
        ValidationPipelineError,
        match="audit counters do not match",
    ):
        run_validation_pipeline(
            pipeline_engine,
            run_id=1,
        )

    with pipeline_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT
                    status,
                    records_extracted,
                    records_loaded,
                    records_rejected
                FROM etl_pipeline_runs
                WHERE run_id = 1
                """
            )
        ).mappings().one()

    assert audit["status"] == "FAILED"
    assert audit["records_extracted"] == 9
    assert audit["records_loaded"] == 8
    assert audit["records_rejected"] == 0
