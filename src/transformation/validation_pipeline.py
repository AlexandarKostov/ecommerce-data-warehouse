"""
End-to-end validation and reconciliation pipeline.

Reads one ETL run from staging, validates all five datasets,
reconciles dependent records, persists rejections, and finalizes
the ETL audit record.

The rejected-record inserts and final SUCCESS audit update share
one database transaction.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from src.extraction.csv_extractor import SOURCE_DATASETS
from src.loading.rejected_records_loader import (
    persist_rejected_records,
)
from src.loading.staging_loader import run_staging_load
from src.transformation.reconciliation.orders import reconcile_orders
from src.transformation.validation import (
    validate_customers,
    validate_order_items,
    validate_orders,
    validate_payments,
    validate_products,
)


class ValidationPipelineError(Exception):
    """Raised when validation or reconciliation cannot complete."""


def _normalize_identifier(value: Any) -> str | None:
    """Normalize an identifier without changing its case."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip()

    return normalized or None


def _get_valid_identifiers(
    dataframe: pd.DataFrame,
    column: str,
) -> set[str]:
    """Extract normalized identifiers from accepted records."""

    return {
        identifier
        for identifier in (
            _normalize_identifier(value)
            for value in dataframe[column]
        )
        if identifier is not None
    }


def _calculate_order_totals(
    valid_order_items: pd.DataFrame,
) -> dict[str, Decimal]:
    """
    Calculate net order totals from individually valid order items.

    Formula:
        quantity * unit_price - discount_amount

    All financial arithmetic uses Decimal.
    """

    totals: dict[str, Decimal] = {}

    for _, row in valid_order_items.iterrows():
        order_id = _normalize_identifier(row["source_order_id"])

        if order_id is None:
            raise ValidationPipelineError(
                "A validated order item has no order identifier."
            )

        try:
            quantity = Decimal(str(row["quantity"]).strip())
            unit_price = Decimal(str(row["unit_price"]).strip())
            discount = Decimal(str(row["discount_amount"]).strip())

            item_total = quantity * unit_price - discount

        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationPipelineError(
                f"Could not calculate the total for order {order_id}."
            ) from exc

        if not item_total.is_finite():
            raise ValidationPipelineError(
                f"Order {order_id} has a non-finite item total."
            )

        totals[order_id] = (
            totals.get(order_id, Decimal("0")) + item_total
        )

    return totals


def _load_staging_datasets(
    engine: Engine,
    run_id: int,
) -> dict[str, pd.DataFrame]:
    """Load all staging records belonging to one ETL run."""

    datasets = {}

    with engine.connect() as connection:
        for staging_table, configuration in SOURCE_DATASETS.items():
            columns = (
                ["staging_id", "etl_run_id"]
                + configuration["columns"]
                + ["source_file"]
            )

            column_sql = ", ".join(
                f"`{column}`" for column in columns
            )

            statement = text(
                f"""
                SELECT {column_sql}
                FROM `{staging_table}`
                WHERE etl_run_id = :run_id
                ORDER BY staging_id
                """
            )

            dataframe = pd.read_sql_query(
                statement,
                connection,
                params={"run_id": run_id},
            )

            datasets[staging_table] = dataframe

    return datasets


def _validate_staging_completeness(
    audit: dict[str, Any],
    datasets: dict[str, pd.DataFrame],
) -> None:
    """
    Verify audit counters and staging records before validation.

    Every configured source dataset must contain records, and the
    total number of retrieved staging rows must match records_loaded.
    """

    records_extracted = audit["records_extracted"]
    records_loaded = audit["records_loaded"]

    if records_extracted != records_loaded:
        raise ValidationPipelineError(
            "ETL audit counters do not match. "
            f"Extracted: {records_extracted}; "
            f"loaded: {records_loaded}."
        )

    if records_loaded <= 0:
        raise ValidationPipelineError(
            "The ETL run contains no successfully loaded records."
        )

    expected_tables = set(SOURCE_DATASETS)
    actual_tables = set(datasets)

    if actual_tables != expected_tables:
        raise ValidationPipelineError(
            "The staging datasets do not match the expected schema. "
            f"Missing: {sorted(expected_tables - actual_tables)}; "
            f"unexpected: {sorted(actual_tables - expected_tables)}."
        )

    empty_tables = [
        table
        for table in SOURCE_DATASETS
        if datasets[table].empty
    ]

    if empty_tables:
        raise ValidationPipelineError(
            "Staging datasets are unexpectedly empty: "
            f"{sorted(empty_tables)}."
        )

    actual_loaded_count = sum(
        len(dataframe)
        for dataframe in datasets.values()
    )

    if actual_loaded_count != records_loaded:
        raise ValidationPipelineError(
            "Staging record count mismatch. "
            f"Audit records_loaded: {records_loaded}; "
            f"actual staging records: {actual_loaded_count}."
        )


def _validate_and_reconcile(
    datasets: dict[str, pd.DataFrame],
):
    """Execute individual validation and cross-dataset reconciliation."""

    expected_tables = set(SOURCE_DATASETS)

    if set(datasets) != expected_tables:
        raise ValidationPipelineError(
            "The staging datasets do not match the expected schema."
        )

    # Customers and products.
    customer_result = validate_customers(
        datasets["stg_customers"]
    )

    product_result = validate_products(
        datasets["stg_products"]
    )

    valid_customer_ids = _get_valid_identifiers(
        customer_result.valid_records,
        "source_customer_id",
    )

    valid_product_ids = _get_valid_identifiers(
        product_result.valid_records,
        "source_product_id",
    )

    # Orders.
    order_result = validate_orders(
        datasets["stg_orders"],
        valid_customer_ids,
    )

    valid_order_ids = _get_valid_identifiers(
        order_result.valid_records,
        "source_order_id",
    )

    # Order items.
    order_item_result = validate_order_items(
        datasets["stg_order_items"],
        valid_order_ids,
        valid_product_ids,
    )

    # Calculate expected totals from individually valid items.
    expected_order_totals = _calculate_order_totals(
        order_item_result.valid_records
    )

    payment_order_ids = (
        valid_order_ids & set(expected_order_totals)
    )

    valid_order_dates = {}

    for _, order in order_result.valid_records.iterrows():
        order_id = _normalize_identifier(
            order["source_order_id"]
        )

        if order_id in payment_order_ids:
            valid_order_dates[order_id] = str(
                order["order_date"]
            ).strip()

    payment_order_totals = {
        order_id: expected_order_totals[order_id]
        for order_id in payment_order_ids
    }

    # Payments.
    payment_result = validate_payments(
        datasets["stg_payments"],
        payment_order_ids,
        valid_order_dates,
        payment_order_totals,
    )

    # Cross-dataset reconciliation.
    reconciliation = reconcile_orders(
        orders=order_result,
        order_items=order_item_result,
        payments=payment_result,
    )

    rejected_datasets = {
        "stg_customers": customer_result.rejected_records,
        "stg_products": product_result.rejected_records,
        "stg_orders": reconciliation.rejected_orders,
        "stg_order_items": reconciliation.rejected_order_items,
        "stg_payments": reconciliation.rejected_payments,
    }

    valid_datasets = {
        "stg_customers": customer_result.valid_records,
        "stg_products": product_result.valid_records,
        "stg_orders": reconciliation.valid_orders,
        "stg_order_items": reconciliation.valid_order_items,
        "stg_payments": reconciliation.valid_payments,
    }

    return valid_datasets, rejected_datasets


def _get_audit_record(
    engine: Engine,
    run_id: int,
) -> dict[str, Any]:
    """Retrieve an ETL audit record that is eligible for validation."""

    statement = text(
        """
        SELECT
            run_id,
            status,
            records_extracted,
            records_loaded,
            records_rejected
        FROM etl_pipeline_runs
        WHERE run_id = :run_id
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            statement,
            {"run_id": run_id},
        ).mappings().one_or_none()

    if row is None:
        raise ValidationPipelineError(
            f"ETL run {run_id} does not exist."
        )

    audit = dict(row)

    if audit["status"] != "RUNNING":
        if audit["status"] == "SUCCESS":
            raise ValidationPipelineError(
                f"ETL run {run_id} has already been finalized "
                "successfully and cannot be validated again."
            )

        raise ValidationPipelineError(
            f"ETL run {run_id} cannot be validated because "
            f"its current status is {audit['status']}."
        )

    return audit


def _mark_validation_failed(
    engine: Engine,
    run_id: int,
    error_message: str,
) -> None:
    """Mark a RUNNING audit record as FAILED."""

    statement = text(
        """
        UPDATE etl_pipeline_runs
        SET
            finished_at = CURRENT_TIMESTAMP,
            status = 'FAILED',
            error_message = :error_message
        WHERE run_id = :run_id
          AND status = 'RUNNING'
        """
    )

    with engine.begin() as connection:
        result = connection.execute(
            statement,
            {
                "run_id": run_id,
                "error_message": error_message[:60_000],
            },
        )

    if result.rowcount != 1:
        raise ValidationPipelineError(
            f"Could not mark ETL run {run_id} as FAILED. "
            "The run may no longer be in RUNNING status."
        )


def run_validation_pipeline(
    engine: Engine,
    run_id: int,
) -> dict[str, Any]:
    """
    Validate and reconcile staging records for an existing ETL run.

    Only RUNNING runs are eligible.

    Rejected-record persistence and the final SUCCESS audit update
    are committed atomically.

    If validation or persistence fails, the RUNNING audit record
    is marked FAILED.

    Returns:
        Validation summary with valid and rejected record counts.
    """

    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
    ):
        raise ValidationPipelineError(
            "run_id must be a positive integer."
        )

    # Check eligibility outside the failure-handling block.
    # Unknown, SUCCESS, and FAILED runs must not be modified.
    audit = _get_audit_record(engine, run_id)

    try:
        datasets = _load_staging_datasets(
            engine,
            run_id,
        )

        _validate_staging_completeness(
            audit=audit,
            datasets=datasets,
        )

        valid_datasets, rejected_datasets = (
            _validate_and_reconcile(datasets)
        )

        records_rejected = sum(
            len(dataframe)
            for dataframe in rejected_datasets.values()
        )

        rejection_issues = sum(
            len(reasons)
            for dataframe in rejected_datasets.values()
            if not dataframe.empty
            for reasons in dataframe["rejection_reasons"]
        )

        # Deletion, insertion, and SUCCESS update share one transaction.
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM etl_rejected_records
                    WHERE etl_run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            )

            persisted_count = persist_rejected_records(
                connection=connection,
                run_id=run_id,
                rejected_datasets=rejected_datasets,
            )

            if persisted_count != records_rejected:
                raise ValidationPipelineError(
                    "Rejected-record count mismatch. "
                    f"Expected: {records_rejected}; "
                    f"persisted: {persisted_count}."
                )

            update_result = connection.execute(
                text(
                    """
                    UPDATE etl_pipeline_runs
                    SET
                        finished_at = CURRENT_TIMESTAMP,
                        status = 'SUCCESS',
                        records_rejected = :records_rejected,
                        error_message = NULL
                    WHERE run_id = :run_id
                      AND status = 'RUNNING'
                    """
                ),
                {
                    "run_id": run_id,
                    "records_rejected": records_rejected,
                },
            )

            if update_result.rowcount != 1:
                raise ValidationPipelineError(
                    f"Could not finalize ETL run {run_id}. "
                    "The run may no longer be in RUNNING status."
                )

        return {
            "run_id": run_id,
            "status": "SUCCESS",
            "records_extracted": audit["records_extracted"],
            "records_loaded": audit["records_loaded"],
            "records_rejected": records_rejected,
            "rejection_issues": rejection_issues,
            "valid_by_table": {
                table: len(dataframe)
                for table, dataframe in valid_datasets.items()
            },
            "rejected_by_table": {
                table: len(dataframe)
                for table, dataframe in rejected_datasets.items()
            },
        }

    except Exception as error:
        try:
            _mark_validation_failed(
                engine=engine,
                run_id=run_id,
                error_message=str(error),
            )

        except Exception as audit_error:
            raise ValidationPipelineError(
                f"Validation of ETL run {run_id} failed: {error}. "
                f"Audit update also failed: {audit_error}"
            ) from error

        raise ValidationPipelineError(
            f"Validation of ETL run {run_id} failed: {error}"
        ) from error


def run_full_etl_pipeline(
    engine: Engine,
    data_directory=None,
) -> dict[str, Any]:
    """
    Execute extraction, staging, validation, and reconciliation.

    Staging remains RUNNING until validation and rejected-record
    persistence complete successfully.
    """

    staging_result = run_staging_load(
        engine=engine,
        data_directory=data_directory,
        finalize_run=False,
    )

    validation_result = run_validation_pipeline(
        engine=engine,
        run_id=staging_result["run_id"],
    )

    return {
        **staging_result,
        **validation_result,
        "datasets": staging_result["datasets"],
    }