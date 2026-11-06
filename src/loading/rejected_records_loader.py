"""
Rejected-record persistence module.

Persists validation and reconciliation rejections to the
etl_rejected_records audit table.

The caller owns the database transaction. This allows rejected
records and the ETL run's final audit status to be committed atomically.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


SOURCE_IDENTIFIER_COLUMNS = {
    "stg_customers": "source_customer_id",
    "stg_products": "source_product_id",
    "stg_orders": "source_order_id",
    "stg_order_items": "source_order_item_id",
    "stg_payments": "source_payment_id",
}

STAGING_METADATA_COLUMNS = {
    "staging_id",
    "etl_run_id",
    "loaded_at",
}

REQUIRED_REJECTION_COLUMNS = {
    "staging_id",
    "rejection_reasons",
}


class RejectedRecordsLoadError(Exception):
    """Raised when rejected records cannot be persisted."""


def _json_default(value: Any) -> Any:
    """Convert supported Python and pandas values to JSON-compatible data."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if hasattr(value, "item"):
        return value.item()

    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable."
    )


def _serialize_json(value: Any) -> str:
    """Serialize a value as JSON, rejecting non-standard NaN values."""

    try:
        return json.dumps(
            value,
            default=_json_default,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RejectedRecordsLoadError(
            f"Could not serialize rejected-record data: {exc}"
        ) from exc


def _validate_rejected_dataframe(
    source_table: str,
    dataframe: pd.DataFrame,
) -> str:
    """Validate a rejected DataFrame and return its source ID column."""

    if source_table not in SOURCE_IDENTIFIER_COLUMNS:
        raise RejectedRecordsLoadError(
            f"Unsupported source table: {source_table}."
        )

    if not isinstance(dataframe, pd.DataFrame):
        raise RejectedRecordsLoadError(
            f"Rejected records for {source_table} must be a DataFrame."
        )

    source_id_column = SOURCE_IDENTIFIER_COLUMNS[source_table]

    missing_columns = {"staging_id"} - set(dataframe.columns)

    if source_id_column not in dataframe.columns:
        missing_columns.add(source_id_column)

    # Rejection reasons are required only when records exist.
    if (
        not dataframe.empty
        and "rejection_reasons" not in dataframe.columns
    ):
        missing_columns.add("rejection_reasons")

    if missing_columns:
        raise RejectedRecordsLoadError(
            f"{source_table} is missing required columns: "
            f"{sorted(missing_columns)}."
        )

    if dataframe.empty:
        return source_id_column

    if dataframe["staging_id"].isna().any():
        raise RejectedRecordsLoadError(
            f"{source_table} contains a rejected record without staging_id."
        )

    if dataframe["staging_id"].duplicated().any():
        raise RejectedRecordsLoadError(
            f"{source_table} contains duplicate staging_id values."
        )

    return source_id_column

def persist_rejected_records(
    connection: Connection,
    run_id: int,
    rejected_datasets: Mapping[str, pd.DataFrame],
) -> int:
    """
    Persist rejected records for one ETL run.

    Expected mapping:
        {
            "stg_customers": rejected_customers,
            "stg_products": rejected_products,
            "stg_orders": rejected_orders,
            "stg_order_items": rejected_order_items,
            "stg_payments": rejected_payments,
        }

    One database row is created per rejected physical staging record.
    Multiple rejection reasons are stored together as a JSON array.

    The supplied connection must already be inside a transaction.
    This function does not commit or roll back that transaction.

    Returns:
        Number of rejected physical records persisted.
    """

    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise RejectedRecordsLoadError(
            "run_id must be a positive integer."
        )

    if not isinstance(rejected_datasets, Mapping):
        raise RejectedRecordsLoadError(
            "rejected_datasets must be a mapping of source tables to DataFrames."
        )

    unexpected_tables = set(rejected_datasets) - set(
        SOURCE_IDENTIFIER_COLUMNS
    )

    if unexpected_tables:
        raise RejectedRecordsLoadError(
            f"Unsupported source tables: {sorted(unexpected_tables)}."
        )

    insert_statement = text(
        """
        INSERT INTO etl_rejected_records (
            etl_run_id,
            source_table,
            staging_record_id,
            source_record_id,
            rejection_reasons,
            raw_record
        )
        VALUES (
            :etl_run_id,
            :source_table,
            :staging_record_id,
            :source_record_id,
            :rejection_reasons,
            :raw_record
        )
        """
    )

    total_persisted = 0

    for source_table, source_id_column in SOURCE_IDENTIFIER_COLUMNS.items():

        dataframe = rejected_datasets.get(
            source_table,
            pd.DataFrame(
                columns=[
                    "staging_id",
                    source_id_column,
                    "rejection_reasons",
                ]
            ),
        )

        _validate_rejected_dataframe(source_table, dataframe)

        if dataframe.empty:
            continue

        records = []

        for record in dataframe.to_dict(orient="records"):

            staging_id = record["staging_id"]
            reasons = record["rejection_reasons"]

            if not isinstance(reasons, list) or not reasons:
                raise RejectedRecordsLoadError(
                    f"{source_table} staging_id={staging_id} "
                    "must contain a non-empty rejection_reasons list."
                )

            for reason in reasons:
                if not isinstance(reason, dict):
                    raise RejectedRecordsLoadError(
                        f"{source_table} staging_id={staging_id} "
                        "contains an invalid rejection reason."
                    )

                if not {"code", "field", "message"}.issubset(reason):
                    raise RejectedRecordsLoadError(
                        f"{source_table} staging_id={staging_id} "
                        "contains an incomplete rejection reason."
                    )

            raw_record = {
                key: value
                for key, value in record.items()
                if key not in STAGING_METADATA_COLUMNS
                and key != "rejection_reasons"
            }

            records.append(
                {
                    "etl_run_id": run_id,
                    "source_table": source_table,
                    "staging_record_id": int(staging_id),
                    "source_record_id": (
                        None
                        if pd.isna(record[source_id_column])
                        else str(record[source_id_column])
                    ),
                    "rejection_reasons": _serialize_json(reasons),
                    "raw_record": _serialize_json(raw_record),
                }
            )

        connection.execute(insert_statement, records)
        total_persisted += len(records)

    return total_persisted
