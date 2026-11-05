
"""
Tests for the ecommerce staging loader.

Uses isolated in-memory SQLite databases.
No tests modify the real MySQL warehouse.
"""

import pandas as pd
import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.extraction.csv_extractor import (
    SOURCE_DATASETS,
    CSVExtractionError,
)

from src.loading import staging_loader
from src.loading.staging_loader import (
    StagingLoadError,
    run_staging_load,
)


@pytest.fixture
def test_engine():
    """Create an isolated in-memory database for each test."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:

        connection.execute(
            text(
                """
                CREATE TABLE etl_pipeline_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_name VARCHAR(100) NOT NULL,
                    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
                    records_extracted BIGINT NOT NULL DEFAULT 0,
                    records_loaded BIGINT NOT NULL DEFAULT 0,
                    records_rejected BIGINT NOT NULL DEFAULT 0,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        for staging_table, configuration in SOURCE_DATASETS.items():

            columns = configuration["columns"] + ["source_file"]

            column_definitions = [
                "`staging_id` INTEGER PRIMARY KEY AUTOINCREMENT",
                "`etl_run_id` BIGINT",
            ]

            for column in columns:
                column_definitions.append(
                    f"`{column}` VARCHAR(255)"
                )

            column_definitions.append(
                "`loaded_at` DATETIME DEFAULT CURRENT_TIMESTAMP"
            )

            connection.execute(
                text(
                    f"""
                    CREATE TABLE `{staging_table}` (
                        {", ".join(column_definitions)}
                    )
                    """
                )
            )

    yield engine

    engine.dispose()


@pytest.fixture
def sample_datasets():
    """Build small source datasets matching the extractor schema."""

    datasets = {}

    for staging_table, configuration in SOURCE_DATASETS.items():

        file_name = configuration["file_name"]
        columns = configuration["columns"] + ["source_file"]

        records = []

        for record_number in range(2):
            record = {
                column: f"value_{record_number}"
                for column in configuration["columns"]
            }

            record["source_file"] = file_name
            records.append(record)

        datasets[staging_table] = pd.DataFrame(
            records,
            columns=columns,
        )

    return datasets


def get_audit_record(engine: Engine, run_id: int) -> dict:
    """Retrieve one ETL audit record."""

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT
                    run_id,
                    status,
                    records_extracted,
                    records_loaded,
                    records_rejected,
                    error_message
                FROM etl_pipeline_runs
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )

        row = result.mappings().one()

    return dict(row)


def get_staging_record_count(engine: Engine) -> int:
    """Count all records across the five staging tables."""

    total = 0

    with engine.connect() as connection:
        for staging_table in SOURCE_DATASETS:

            result = connection.execute(
                text(
                    f"SELECT COUNT(*) FROM `{staging_table}`"
                )
            )

            total += result.scalar_one()

    return total


def test_successful_staging_load(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """All datasets and the SUCCESS audit record commit together."""

    monkeypatch.setattr(
        staging_loader,
        "extract_csv_files",
        lambda *args, **kwargs: sample_datasets,
    )

    result = run_staging_load(test_engine)

    expected_records = sum(
        len(dataframe)
        for dataframe in sample_datasets.values()
    )

    assert result["status"] == "SUCCESS"
    assert result["records_extracted"] == expected_records
    assert result["records_loaded"] == expected_records
    assert result["records_rejected"] == 0

    audit = get_audit_record(
        test_engine,
        result["run_id"],
    )

    assert audit["status"] == "SUCCESS"
    assert audit["records_extracted"] == expected_records
    assert audit["records_loaded"] == expected_records
    assert audit["records_rejected"] == 0
    assert audit["error_message"] is None

    assert get_staging_record_count(test_engine) == expected_records

    # Every table must contain records belonging to this ETL run.
        # Every table must contain records belonging to this ETL run.
    run_id = result["run_id"]

    with test_engine.connect() as connection:
        for staging_table in SOURCE_DATASETS:

            query_result = connection.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM `{staging_table}`
                    WHERE etl_run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            )

            assert query_result.scalar_one() == 2


def test_extraction_failure_marks_run_failed(
    test_engine,
    monkeypatch,
):
    """An extraction failure must be recorded in the audit table."""

    def raise_extraction_error(*args, **kwargs):
        raise CSVExtractionError("Test source file is missing.")

    monkeypatch.setattr(
        staging_loader,
        "extract_csv_files",
        raise_extraction_error,
    )

    with pytest.raises(
        StagingLoadError,
        match="Test source file is missing",
    ):
        run_staging_load(test_engine)

    with test_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT status, records_loaded, error_message
                FROM etl_pipeline_runs
                """
            )
        ).mappings().one()

    assert audit["status"] == "FAILED"
    assert audit["records_loaded"] == 0
    assert "Test source file is missing" in audit["error_message"]

    assert get_staging_record_count(test_engine) == 0


def test_insert_failure_rolls_back_entire_staging_batch(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """An insert failure must roll back records from every staging table."""

    monkeypatch.setattr(
        staging_loader,
        "extract_csv_files",
        lambda *args, **kwargs: sample_datasets,
    )

    # Force an insert failure when the loader reaches stg_orders.
    with test_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER fail_stg_orders_insert
                BEFORE INSERT ON stg_orders
                BEGIN
                    SELECT RAISE(ABORT, 'Simulated staging insert failure');
                END;
                """
            )
        )

    with pytest.raises(
        StagingLoadError,
        match="Simulated staging insert failure",
    ):
        run_staging_load(test_engine)

    # Earlier inserts must also have been rolled back.
    assert get_staging_record_count(test_engine) == 0

    with test_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT status, records_loaded, error_message
                FROM etl_pipeline_runs
                """
            )
        ).mappings().one()

    assert audit["status"] == "FAILED"
    assert audit["records_loaded"] == 0
    assert "Simulated staging insert failure" in audit["error_message"]


def test_success_audit_failure_rolls_back_staging_batch(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """
    A failure while updating the SUCCESS audit status must also
    roll back all staging inserts.
    """

    monkeypatch.setattr(
        staging_loader,
        "extract_csv_files",
        lambda *args, **kwargs: sample_datasets,
    )

    # Fail only the SUCCESS update. The subsequent FAILED update
    # must remain possible.
    with test_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TRIGGER fail_success_audit_update
                BEFORE UPDATE ON etl_pipeline_runs
                WHEN NEW.status = 'SUCCESS'
                BEGIN
                    SELECT RAISE(ABORT, 'Simulated SUCCESS audit failure');
                END;
                """
            )
        )

    with pytest.raises(
        StagingLoadError,
        match="Simulated SUCCESS audit failure",
    ):
        run_staging_load(test_engine)

    # The staging transaction must have rolled back.
    assert get_staging_record_count(test_engine) == 0

    with test_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT status, records_extracted,
                       records_loaded, error_message
                FROM etl_pipeline_runs
                """
            )
        ).mappings().one()

    # The independent failure update must have succeeded.
    assert audit["status"] == "FAILED"
    assert audit["records_extracted"] == 10
    assert audit["records_loaded"] == 0
    assert "Simulated SUCCESS audit failure" in audit["error_message"]
