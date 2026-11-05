
"""
Staging loader module.

Loads extracted ecommerce source datasets into MySQL staging tables.

Each execution creates a separate ETL audit record. All five staging
datasets and the SUCCESS audit update are committed in one transaction.
"""

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from src.extraction.csv_extractor import (
    SOURCE_DATASETS,
    extract_csv_files,
)


BATCH_SIZE = 1_000


class StagingLoadError(Exception):
    """Raised when staging data cannot be loaded successfully."""


def _create_etl_run(engine: Engine) -> int:
    """
    Create and commit a new RUNNING audit record.

    Returns:
        The generated ETL run ID.
    """

    statement = text(
        """
        INSERT INTO etl_pipeline_runs (pipeline_name, status)
        VALUES (:pipeline_name, 'RUNNING')
        """
    )

    with engine.begin() as connection:
        result = connection.execute(
            statement,
            {"pipeline_name": "ecommerce_data_warehouse"},
        )

        run_id = result.lastrowid

    if run_id is None:
        raise StagingLoadError(
            "Unable to retrieve the newly created ETL run ID."
        )

    return int(run_id)


def _update_etl_run(
    connection: Any,
    run_id: int,
    status: str,
    records_extracted: int,
    records_loaded: int,
    error_message: str | None = None,
) -> None:
    """
    Update an ETL audit record using the caller's transaction.

    The caller controls when this update is committed or rolled back.
    """

    if status not in {"SUCCESS", "FAILED"}:
        raise ValueError(f"Unsupported ETL run status: {status}")

    statement = text(
        """
        UPDATE etl_pipeline_runs
        SET
            finished_at = CURRENT_TIMESTAMP,
            status = :status,
            records_extracted = :records_extracted,
            records_loaded = :records_loaded,
            records_rejected = 0,
            error_message = :error_message
        WHERE run_id = :run_id
        """
    )

    result = connection.execute(
        statement,
        {
            "run_id": run_id,
            "status": status,
            "records_extracted": records_extracted,
            "records_loaded": records_loaded,
            "error_message": (
                error_message[:60_000]
                if error_message
                else None
            ),
        },
    )

    if result.rowcount != 1:
        raise StagingLoadError(
            f"Unable to update ETL audit record {run_id}."
        )


def _validate_extracted_datasets(
    datasets: dict[str, pd.DataFrame],
) -> None:
    """
    Verify that all expected datasets are available and correctly shaped.
    """

    expected_tables = set(SOURCE_DATASETS)
    actual_tables = set(datasets)

    missing_tables = expected_tables - actual_tables
    unexpected_tables = actual_tables - expected_tables

    if missing_tables or unexpected_tables:
        raise StagingLoadError(
            f"Invalid extracted datasets. "
            f"Missing: {sorted(missing_tables)}. "
            f"Unexpected: {sorted(unexpected_tables)}."
        )

    for staging_table, configuration in SOURCE_DATASETS.items():
        dataframe = datasets[staging_table]

        if not isinstance(dataframe, pd.DataFrame):
            raise StagingLoadError(
                f"{staging_table} must contain a pandas DataFrame."
            )

        if dataframe.empty:
            raise StagingLoadError(
                f"Cannot load an empty dataset into {staging_table}."
            )

        expected_columns = (
            configuration["columns"] + ["source_file"]
        )

        if list(dataframe.columns) != expected_columns:
            raise StagingLoadError(
                f"Unexpected columns in {staging_table}. "
                f"Expected: {expected_columns}. "
                f"Received: {list(dataframe.columns)}."
            )


def _insert_dataset(
    connection: Any,
    staging_table: str,
    dataframe: pd.DataFrame,
    run_id: int,
) -> int:
    """
    Insert one extracted dataset into its staging table.

    Inserts are executed in batches using parameterized SQL.
    The caller controls the transaction.
    """

    columns = list(dataframe.columns)
    insert_columns = ["etl_run_id"] + columns

    # Table and column names originate from fixed project configuration.
    column_sql = ", ".join(
        f"`{column}`" for column in insert_columns
    )

    parameter_sql = ", ".join(
        f":{column}" for column in insert_columns
    )

    statement = text(
        f"""
        INSERT INTO `{staging_table}` ({column_sql})
        VALUES ({parameter_sql})
        """
    )

    records = dataframe.to_dict(orient="records")

    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]

        parameters = [
            {
                "etl_run_id": run_id,
                **record,
            }
            for record in batch
        ]

        connection.execute(statement, parameters)

    return len(records)


def _mark_etl_run_failed(
    engine: Engine,
    run_id: int,
    records_extracted: int,
    error_message: str,
) -> None:
    """
    Mark a previously committed RUNNING audit record as FAILED.

    This uses a separate transaction because the staging transaction
    has already been rolled back.
    """

    with engine.begin() as connection:
        _update_etl_run(
            connection=connection,
            run_id=run_id,
            status="FAILED",
            records_extracted=records_extracted,
            records_loaded=0,
            error_message=error_message,
        )


def run_staging_load(
    engine: Engine,
    data_directory: Path | str | None = None,
) -> dict[str, Any]:
    """
    Execute the complete CSV extraction and staging load.

    Processing:
        1. Create an independently committed RUNNING audit record.
        2. Extract all five CSV datasets.
        3. Validate extracted dataset structure.
        4. Load all staging tables in one transaction.
        5. Update the audit record to SUCCESS in that transaction.

    If extraction, validation, loading, or the SUCCESS audit update fails,
    the staging transaction is rolled back and the audit record is marked
    FAILED in a separate transaction.

    Every execution creates a new ETL run.

    Returns:
        Summary containing run ID and record counts.

    Raises:
        StagingLoadError: If extraction, validation, or loading fails.
    """

    run_id = _create_etl_run(engine)

    records_extracted = 0

    try:
        # Extract source datasets.
        if data_directory is None:
            datasets = extract_csv_files()
        else:
            datasets = extract_csv_files(data_directory)

        _validate_extracted_datasets(datasets)

        records_extracted = sum(
            len(dataframe)
            for dataframe in datasets.values()
        )

        records_loaded = 0

        # Staging inserts and SUCCESS audit update are atomic.
        with engine.begin() as connection:

            for staging_table, dataframe in datasets.items():
                inserted_count = _insert_dataset(
                    connection=connection,
                    staging_table=staging_table,
                    dataframe=dataframe,
                    run_id=run_id,
                )

                records_loaded += inserted_count

            if records_loaded != records_extracted:
                raise StagingLoadError(
                    "Record count mismatch. "
                    f"Extracted: {records_extracted}; "
                    f"loaded: {records_loaded}."
                )

            # This update commits together with all staging inserts.
            _update_etl_run(
                connection=connection,
                run_id=run_id,
                status="SUCCESS",
                records_extracted=records_extracted,
                records_loaded=records_loaded,
            )

        return {
            "run_id": run_id,
            "status": "SUCCESS",
            "records_extracted": records_extracted,
            "records_loaded": records_loaded,
            "records_rejected": 0,
            "datasets": {
                table: len(dataframe)
                for table, dataframe in datasets.items()
            },
        }

    except Exception as error:
        # The staging transaction has rolled back automatically.
        try:
            _mark_etl_run_failed(
                engine=engine,
                run_id=run_id,
                records_extracted=records_extracted,
                error_message=str(error),
            )

        except Exception as audit_error:
            raise StagingLoadError(
                f"ETL run {run_id} failed, and its audit record "
                f"could not be updated. Original error: {error}. "
                f"Audit error: {audit_error}"
            ) from error

        raise StagingLoadError(
            f"ETL run {run_id} failed: {error}"
        ) from error
