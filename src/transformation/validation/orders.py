"""
Order dataset validation.

Validates order identifiers, customer references, order dates,
order statuses, and duplicate source order IDs.

The validator is pure: it does not modify input data or access
the database.
"""

from datetime import date, datetime

import pandas as pd

from config.data_generation import REFERENCE_DATE
from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    ValidationResult,
    create_validation_result,
)


REQUIRED_COLUMNS = {
    "source_order_id",
    "source_customer_id",
    "order_date",
    "order_status",
}

VALID_ORDER_STATUSES = {
    "pending",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "returned",
}


def _is_missing(value: object) -> bool:
    """Check whether a scalar value is missing."""

    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_blank(value: object) -> bool:
    """Check whether a value is missing or contains only whitespace."""

    return (
        _is_missing(value)
        or (isinstance(value, str) and not value.strip())
    )


def _normalize_identifier(value: object) -> str:
    """Normalize an identifier for reference and duplicate comparisons."""

    return str(value).strip()


def _parse_order_date(value: object) -> date | None:
    """Parse an order date in the expected YYYY-MM-DD format."""

    if _is_blank(value):
        return None

    try:
        return datetime.strptime(
            str(value).strip(),
            "%Y-%m-%d",
        ).date()
    except (TypeError, ValueError):
        return None


def _get_reference_date() -> date:
    """Read the configured reference date used by data generation."""

    try:
        return datetime.strptime(
            REFERENCE_DATE,
            "%Y-%m-%d",
        ).date()
    except (TypeError, ValueError) as error:
        raise ValidationError(
            "Configured REFERENCE_DATE must use YYYY-MM-DD format."
        ) from error


def validate_orders(
    dataframe: pd.DataFrame,
    valid_customer_ids: set[str] | frozenset[str],
) -> ValidationResult:
    """
    Validate an order dataset against valid customer identifiers.

    Rules:
        - source_order_id must be present and unique.
        - source_customer_id must be present.
        - source_customer_id must exist among valid customer IDs.
        - order_date must be present and use YYYY-MM-DD format.
        - order_date must not be later than REFERENCE_DATE.
        - order_status must be one of the supported warehouse statuses.

    Duplicate handling:
        The first occurrence of a non-empty source order ID
        is retained. Subsequent occurrences are rejected.

        Duplicate comparison ignores leading and trailing
        whitespace but remains case-sensitive.

    Cross-dataset handling:
        Only IDs supplied through valid_customer_ids are accepted.
        The caller must supply IDs from the valid customer records,
        not from the unvalidated customer staging dataset.

    Returns:
        ValidationResult containing valid and rejected records.

    Raises:
        ValidationError: If the input DataFrame, required columns,
                         or valid_customer_ids argument is invalid.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise ValidationError(
            "Order validation input must be a pandas DataFrame."
        )

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise ValidationError(
            "Order dataset is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if not isinstance(valid_customer_ids, (set, frozenset)):
        raise ValidationError(
            "valid_customer_ids must be a set or frozenset "
            "of validated customer IDs."
        )

    normalized_customer_ids = {
        _normalize_identifier(customer_id)
        for customer_id in valid_customer_ids
        if not _is_blank(customer_id)
    }

    reference_date = _get_reference_date()

    issues_by_position: dict[int, list[ValidationIssue]] = {}
    seen_order_ids: set[str] = set()

    for position in range(len(dataframe)):
        record = dataframe.iloc[position]
        issues: list[ValidationIssue] = []

        order_id = record["source_order_id"]
        customer_id = record["source_customer_id"]
        order_date_value = record["order_date"]
        order_status = record["order_status"]

        # Validate the source order identifier.
        if _is_blank(order_id):
            issues.append(
                ValidationIssue(
                    code="MISSING_ORDER_ID",
                    field="source_order_id",
                    message="Order ID is required.",
                )
            )
        else:
            normalized_order_id = _normalize_identifier(order_id)

            if normalized_order_id in seen_order_ids:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_ORDER_ID",
                        field="source_order_id",
                        message=(
                            "Order ID already exists in this dataset. "
                            "The first occurrence is retained."
                        ),
                    )
                )
            else:
                seen_order_ids.add(normalized_order_id)

        # Validate the customer reference.
        if _is_blank(customer_id):
            issues.append(
                ValidationIssue(
                    code="MISSING_CUSTOMER_REFERENCE",
                    field="source_customer_id",
                    message="Order customer reference is required.",
                )
            )
        elif (
            _normalize_identifier(customer_id)
            not in normalized_customer_ids
        ):
            issues.append(
                ValidationIssue(
                    code="INVALID_CUSTOMER_REFERENCE",
                    field="source_customer_id",
                    message=(
                        "Order references a customer that is not "
                        "present in the validated customer dataset."
                    ),
                )
            )

        # Validate the order date.
        if _is_blank(order_date_value):
            issues.append(
                ValidationIssue(
                    code="MISSING_ORDER_DATE",
                    field="order_date",
                    message="Order date is required.",
                )
            )
        else:
            parsed_order_date = _parse_order_date(order_date_value)

            if parsed_order_date is None:
                issues.append(
                    ValidationIssue(
                        code="INVALID_ORDER_DATE",
                        field="order_date",
                        message=(
                            "Order date must be a valid date "
                            "in YYYY-MM-DD format."
                        ),
                    )
                )
            elif parsed_order_date > reference_date:
                issues.append(
                    ValidationIssue(
                        code="FUTURE_ORDER_DATE",
                        field="order_date",
                        message=(
                            "Order date cannot be later than the "
                            "configured reference date."
                        ),
                    )
                )

        # Validate the order status.
        if _is_blank(order_status):
            issues.append(
                ValidationIssue(
                    code="MISSING_ORDER_STATUS",
                    field="order_status",
                    message="Order status is required.",
                )
            )
        elif str(order_status).strip().casefold() not in VALID_ORDER_STATUSES:
            issues.append(
                ValidationIssue(
                    code="INVALID_ORDER_STATUS",
                    field="order_status",
                    message=(
                        "Order status is not a supported warehouse status."
                    ),
                )
            )

        if issues:
            issues_by_position[position] = issues

    return create_validation_result(
        dataframe=dataframe,
        issues_by_position=issues_by_position,
    )