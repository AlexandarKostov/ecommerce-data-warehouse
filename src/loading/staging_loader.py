
"""
Staging loader module.

Loads extracted ecommerce source datasets into MySQL staging tables.

Each execution creates a separate ETL audit record.

The loader supports two execution modes:

1. Finalized loading:
   Staging inserts and the SUCCESS audit update are committed atomically.

2. Deferred finalization:
   Staging inserts and progress counters are committed while the
   audit record remains RUNNING for subsequent validation.
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
PIPELINE_NAME = "ecommerce_data_warehouse"


class StagingLoadError(Exception):
    """Raised when staging data cannot be loaded successfully."""


def _create_etl_run(engine: Engine) -> int:
    """Create and commit a new RUNNING ETL audit record."""

    statement = text(
        """
        INSERT INTO etl_pipeline_runs (pipeline_name, status)
        VALUES (:pipeline_name, 'RUNNING')
        """
    )

    with engine.begin() as connection:
        result = connection.execute(
            statement,
            {"pipeline_name": PIPELINE_NAME},
        )

        run_id = result.lastrowid

    if run_id is None:
        raise StagingLoadError(
            "Unable to retrieve the newly created ETL run ID."
        )

    return int(run_id)


def _record_staging_progress(
    connection: Any,
    run_id: int,
    records_extracted: int,
    records_loaded: int,
) -> None:
    """
    Update staging counters without finalizing the ETL run.

    The audit record must remain RUNNING. The caller controls
    the transaction.
    """

    statement = text(
        """
        UPDATE etl_pipeline_runs
        SET
            records_extracted = :records_extracted,
            records_loaded = :records_loaded
        WHERE run_id = :run_id
          AND status = 'RUNNING'
        """
    )

    result = connection.execute(
        statement,
        {
            "run_id": run_id,
            "records_extracted": records_extracted,
            "records_loaded": records_loaded,
        },
    )

    if result.rowcount != 1:
        raise StagingLoadError(
            f"Unable to record staging progress for ETL run {run_id}."
        )


def _update_etl_run(
    connection: Any,
    run_id: int,
    status: str,
    records_extracted: int,
    records_loaded: int,
    error_message: str | None = None,
) -> None:
    """
    Update the final status of an ETL audit record.

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
        AND status = 'RUNNING'
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
    """Validate extracted datasets against the source configuration."""

    expected_tables = set(SOURCE_DATASETS)
    actual_tables = set(datasets)

    missing_tables = expected_tables - actual_tables
    unexpected_tables = actual_tables - expected_tables

    if missing_tables or unexpected_tables:
        raise StagingLoadError(
            "Invalid extracted datasets. "
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
    Insert one dataset into its staging table in batches.

    Table and column names originate from the fixed project
    configuration. Record values use parameterized SQL.
    """

    columns = list(dataframe.columns)
    insert_columns = ["etl_run_id", *columns]

    column_sql = ", ".join(
        f"`{column}`"
        for column in insert_columns
    )

    parameter_sql = ", ".join(
        f":{column}"
        for column in insert_columns
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
    Mark a committed RUNNING audit record as FAILED.

    This uses an independent transaction because the staging
    transaction has already been rolled back.
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
    finalize_run: bool = True,
) -> dict[str, Any]:
    """
    Execute extraction and staging loading.

    With finalize_run=True:
        Staging inserts and the SUCCESS audit update commit together.

    With finalize_run=False:
        Staging inserts and progress counters commit together.
        The audit record remains RUNNING for validation.

    Any staging failure rolls back the staging transaction and
    marks the audit record FAILED.
    """

    if not isinstance(finalize_run, bool):
        raise ValueError("finalize_run must be a boolean.")

    run_id = _create_etl_run(engine)
    records_extracted = 0

    try:
        datasets = (
            extract_csv_files()
            if data_directory is None
            else extract_csv_files(data_directory)
        )

        _validate_extracted_datasets(datasets)

        records_extracted = sum(
            len(dataframe)
            for dataframe in datasets.values()
        )

        records_loaded = 0

        with engine.begin() as connection:
            for staging_table, dataframe in datasets.items():
                records_loaded += _insert_dataset(
                    connection=connection,
                    staging_table=staging_table,
                    dataframe=dataframe,
                    run_id=run_id,
                )

            if records_loaded != records_extracted:
                raise StagingLoadError(
                    "Record count mismatch. "
                    f"Extracted: {records_extracted}; "
                    f"loaded: {records_loaded}."
                )

            if finalize_run:
                _update_etl_run(
                    connection=connection,
                    run_id=run_id,
                    status="SUCCESS",
                    records_extracted=records_extracted,
                    records_loaded=records_loaded,
                )
            else:
                _record_staging_progress(
                    connection=connection,
                    run_id=run_id,
                    records_extracted=records_extracted,
                    records_loaded=records_loaded,
                )

        return {
            "run_id": run_id,
            "status": "SUCCESS" if finalize_run else "RUNNING",
            "records_extracted": records_extracted,
            "records_loaded": records_loaded,
            "records_rejected": 0,
            "datasets": {
                table: len(dataframe)
                for table, dataframe in datasets.items()
            },
        }

    except Exception as error:
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
