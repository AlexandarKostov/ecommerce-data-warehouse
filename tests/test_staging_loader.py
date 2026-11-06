
"""
Tests for the ecommerce staging loader.

All tests use isolated in-memory SQLite databases.
The production MySQL warehouse is never modified.
"""

import pandas as pd
import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.extraction.csv_extractor import (
    CSVExtractionError,
    SOURCE_DATASETS,
)
from src.loading import staging_loader
from src.loading.staging_loader import (
    StagingLoadError,
    run_staging_load,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def test_engine():
    """Create an isolated SQLite database with the required ETL tables."""

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

            column_definitions.extend(
                f"`{column}` VARCHAR(255)"
                for column in columns
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
    """Create small datasets matching the extraction configuration."""

    datasets = {}

    for staging_table, configuration in SOURCE_DATASETS.items():
        columns = configuration["columns"] + ["source_file"]
        file_name = configuration["file_name"]

        records = [
            {
                **{
                    column: f"value_{record_number}"
                    for column in configuration["columns"]
                },
                "source_file": file_name,
            }
            for record_number in range(2)
        ]

        datasets[staging_table] = pd.DataFrame(
            records,
            columns=columns,
        )

    return datasets


# ---------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------


def get_audit_record(engine: Engine, run_id: int) -> dict:
    """Retrieve an ETL audit record by run ID."""

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

        return dict(result.mappings().one())


def get_staging_record_count(engine: Engine) -> int:
    """Return the total number of records across staging tables."""

    with engine.connect() as connection:
        return sum(
            connection.execute(
                text(f"SELECT COUNT(*) FROM `{staging_table}`")
            ).scalar_one()
            for staging_table in SOURCE_DATASETS
        )


def patch_extraction(monkeypatch, datasets):
    """Replace CSV extraction with controlled test datasets."""

    monkeypatch.setattr(
        staging_loader,
        "extract_csv_files",
        lambda *args, **kwargs: datasets,
    )


def create_trigger(engine: Engine, statement: str) -> None:
    """Create a SQLite trigger used to simulate database failures."""

    with engine.begin() as connection:
        connection.execute(text(statement))


# ---------------------------------------------------------------------
# Successful loading
# ---------------------------------------------------------------------


def test_successful_staging_load(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """All staging datasets and the SUCCESS audit update commit together."""

    patch_extraction(monkeypatch, sample_datasets)

    result = run_staging_load(test_engine)

    expected_records = sum(
        len(dataframe)
        for dataframe in sample_datasets.values()
    )

    assert result["status"] == "SUCCESS"
    assert result["records_extracted"] == expected_records
    assert result["records_loaded"] == expected_records
    assert result["records_rejected"] == 0

    audit = get_audit_record(test_engine, result["run_id"])

    assert audit["status"] == "SUCCESS"
    assert audit["records_extracted"] == expected_records
    assert audit["records_loaded"] == expected_records
    assert audit["records_rejected"] == 0
    assert audit["error_message"] is None

    assert get_staging_record_count(test_engine) == expected_records

    with test_engine.connect() as connection:
        for staging_table in SOURCE_DATASETS:
            count = connection.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM `{staging_table}`
                    WHERE etl_run_id = :run_id
                    """
                ),
                {"run_id": result["run_id"]},
            ).scalar_one()

            assert count == 2


def test_deferred_finalization_keeps_run_running(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """Staging commits while the audit run remains RUNNING."""

    patch_extraction(monkeypatch, sample_datasets)

    result = run_staging_load(
        test_engine,
        finalize_run=False,
    )

    expected_records = sum(
        len(dataframe)
        for dataframe in sample_datasets.values()
    )

    assert result["status"] == "RUNNING"
    assert result["records_loaded"] == expected_records

    audit = get_audit_record(test_engine, result["run_id"])

    assert audit["status"] == "RUNNING"
    assert audit["records_loaded"] == expected_records
    assert audit["records_rejected"] == 0
    assert audit["error_message"] is None

    assert get_staging_record_count(test_engine) == expected_records


# ---------------------------------------------------------------------
# Extraction failures
# ---------------------------------------------------------------------


def test_extraction_failure_marks_run_failed(
    test_engine,
    monkeypatch,
):
    """Extraction failures are recorded in the ETL audit table."""

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


# ---------------------------------------------------------------------
# Transaction rollback
# ---------------------------------------------------------------------


def test_insert_failure_rolls_back_entire_staging_batch(
    test_engine,
    sample_datasets,
    monkeypatch,
):
    """An insert failure rolls back records from every staging table."""

    patch_extraction(monkeypatch, sample_datasets)

    create_trigger(
        test_engine,
        """
        CREATE TRIGGER fail_stg_orders_insert
        BEFORE INSERT ON stg_orders
        BEGIN
            SELECT RAISE(ABORT, 'Simulated staging insert failure');
        END;
        """,
    )

    with pytest.raises(
        StagingLoadError,
        match="Simulated staging insert failure",
    ):
        run_staging_load(test_engine)

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
    """A failed SUCCESS audit update also rolls back staging inserts."""

    patch_extraction(monkeypatch, sample_datasets)

    create_trigger(
        test_engine,
        """
        CREATE TRIGGER fail_success_audit_update
        BEFORE UPDATE ON etl_pipeline_runs
        WHEN NEW.status = 'SUCCESS'
        BEGIN
            SELECT RAISE(ABORT, 'Simulated SUCCESS audit failure');
        END;
        """,
    )

    with pytest.raises(
        StagingLoadError,
        match="Simulated SUCCESS audit failure",
    ):
        run_staging_load(test_engine)

    assert get_staging_record_count(test_engine) == 0

    with test_engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT
                    status,
                    records_extracted,
                    records_loaded,
                    error_message
                FROM etl_pipeline_runs
                """
            )
        ).mappings().one()

    assert audit["status"] == "FAILED"
    assert audit["records_extracted"] == 10
    assert audit["records_loaded"] == 0
    assert "Simulated SUCCESS audit failure" in audit["error_message"]
