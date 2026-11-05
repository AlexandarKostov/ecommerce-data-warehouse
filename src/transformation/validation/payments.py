
"""
Payment transaction validation.

Validates payment records against accepted orders and their
calculated net order totals.

The validator is pure:
- It does not modify the input DataFrame.
- It does not access the database.
- It does not write rejected records.
- It returns valid and rejected records through ValidationResult.
"""

from collections.abc import Mapping, Set
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.transformation.validation.orders import REFERENCE_DATE
from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    create_validation_result,
)


REQUIRED_COLUMNS = [
    "source_payment_id",
    "source_order_id",
    "payment_method",
    "payment_status",
    "payment_date",
    "payment_amount",
]


ALLOWED_PAYMENT_METHODS = {
    "Credit Card",
    "Debit Card",
    "PayPal",
    "Bank Transfer",
    "Cash on Delivery",
}


ALLOWED_PAYMENT_STATUSES = {
    "Completed",
    "Failed",
    "Pending",
    "Refunded",
}


def _is_missing(value) -> bool:
    """Return whether a value is missing."""

    if value is None:
        return True

    try:
        result = pd.isna(value)

        return bool(result)

    except (TypeError, ValueError):
        return False


def _is_blank(value) -> bool:
    """Return whether a value is missing or contains only whitespace."""

    return _is_missing(value) or (
        isinstance(value, str) and not value.strip()
    )


def _normalize_identifier(value) -> str | None:
    """Normalize an identifier without changing its case."""

    if _is_blank(value):
        return None

    return str(value).strip()


def _parse_decimal(value) -> Decimal | None:
    """Parse a finite Decimal value."""

    if _is_blank(value):
        return None

    try:
        amount = Decimal(str(value).strip())

    except (InvalidOperation, TypeError, ValueError):
        return None

    if not amount.is_finite():
        return None

    return amount


def _parse_date(value) -> date | None:
    """Parse a strict YYYY-MM-DD date."""

    if _is_blank(value):
        return None

    try:
        parsed_date = date.fromisoformat(str(value).strip())

    except (TypeError, ValueError):
        return None

    # Require the original representation to be canonical ISO format.
    if parsed_date.isoformat() != str(value).strip():
        return None

    return parsed_date


def _normalize_reference_mapping(
    mapping: Mapping,
    mapping_name: str,
) -> dict:
    """Normalize mapping keys and reject duplicate normalized keys."""

    normalized = {}

    for key, value in mapping.items():

        normalized_key = _normalize_identifier(key)

        if normalized_key is None:
            raise ValidationError(
                f"{mapping_name} contains a missing identifier."
            )

        if normalized_key in normalized:
            raise ValidationError(
                f"{mapping_name} contains duplicate normalized identifiers."
            )

        normalized[normalized_key] = value

    return normalized


def validate_payments(
    dataframe: pd.DataFrame,
    valid_order_ids: Set[str],
    valid_order_dates: Mapping[str, date | str],
    expected_order_totals: Mapping[str, Decimal | str | int | float],
):
    """
    Validate payment transactions.

    Parameters
    ----------
    dataframe:
        Payment staging records.

    valid_order_ids:
        Set of accepted source order identifiers.

    valid_order_dates:
        Mapping of accepted source order IDs to their validated order dates.

    expected_order_totals:
        Mapping of accepted source order IDs to their calculated net
        order totals.

        Each payment attempt, including failed and refunded transactions,
        must represent the full net order amount.

    Returns
    -------
    ValidationResult
        Contains valid records, rejected records and validation counts.

    Notes
    -----
    Duplicate payment identifiers use first-occurrence canonical handling.
    The first occurrence remains canonical even if it contains another
    validation error. Later occurrences are rejected as duplicates.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise ValidationError(
            "Payments input must be a pandas DataFrame."
        )

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValidationError(
            "Payments DataFrame is missing columns: "
            + ", ".join(missing_columns)
        )

    if not isinstance(valid_order_ids, Set):
        raise ValidationError(
            "valid_order_ids must be a set or frozenset."
        )

    if not isinstance(valid_order_dates, Mapping):
        raise ValidationError(
            "valid_order_dates must be a mapping."
        )

    if not isinstance(expected_order_totals, Mapping):
        raise ValidationError(
            "expected_order_totals must be a mapping."
        )

    normalized_order_ids = {
        normalized_id
        for order_id in valid_order_ids
        if (normalized_id := _normalize_identifier(order_id)) is not None
    }

    if len(normalized_order_ids) != len(valid_order_ids):
        raise ValidationError(
            "valid_order_ids contains missing or invalid identifiers."
        )

    order_dates = _normalize_reference_mapping(
        valid_order_dates,
        "valid_order_dates",
    )

    order_totals = _normalize_reference_mapping(
        expected_order_totals,
        "expected_order_totals",
    )

    missing_dates = normalized_order_ids - set(order_dates)
    missing_totals = normalized_order_ids - set(order_totals)

    if missing_dates:
        raise ValidationError(
            "valid_order_dates does not contain dates for all valid orders."
        )

    if missing_totals:
        raise ValidationError(
            "expected_order_totals does not contain totals for all valid orders."
        )

    # Validate the reference data before processing payment rows.
    parsed_order_dates = {}

    for order_id in normalized_order_ids:

        order_date = _parse_date(order_dates[order_id])

        if order_date is None:
            raise ValidationError(
                f"Invalid validated order date for order {order_id}."
            )

        if order_date > date.fromisoformat(REFERENCE_DATE):
            raise ValidationError(
                f"Validated order {order_id} has a date after the reference date."
            )

        parsed_order_dates[order_id] = order_date

    parsed_order_totals = {}

    for order_id in normalized_order_ids:

        order_total = _parse_decimal(order_totals[order_id])

        if order_total is None or order_total <= 0:
            raise ValidationError(
                f"Invalid expected order total for order {order_id}."
            )

        parsed_order_totals[order_id] = order_total

    reference_date = date.fromisoformat(REFERENCE_DATE)

    issues_by_position = {}
    seen_payment_ids = set()

    for position, (_, row) in enumerate(dataframe.iterrows()):

        issues = []

        def add_issue(code: str, field: str, message: str) -> None:
            issues.append(
                ValidationIssue(
                    code=code,
                    field=field,
                    message=message,
                )
            )

        # ---------------------------------------------------------
        # Payment identifier
        # ---------------------------------------------------------

        payment_id = _normalize_identifier(
            row["source_payment_id"]
        )

        if payment_id is None:

            add_issue(
                "missing_payment_id",
                "source_payment_id",
                "Payment identifier is required.",
            )

        elif payment_id in seen_payment_ids:

            add_issue(
                "duplicate_payment_id",
                "source_payment_id",
                f"Payment identifier {payment_id} is duplicated.",
            )

        else:

            # First occurrence remains canonical even if another
            # validation rule rejects this record.
            seen_payment_ids.add(payment_id)

        # ---------------------------------------------------------
        # Order reference
        # ---------------------------------------------------------

        order_id = _normalize_identifier(
            row["source_order_id"]
        )

        if order_id is None:

            add_issue(
                "missing_order_reference",
                "source_order_id",
                "Payment must reference an order.",
            )

        elif order_id not in normalized_order_ids:

            add_issue(
                "invalid_order_reference",
                "source_order_id",
                f"Order reference {order_id} does not exist "
                "in the accepted orders.",
            )

        # ---------------------------------------------------------
        # Payment method
        # ---------------------------------------------------------

        payment_method = (
            None
            if _is_blank(row["payment_method"])
            else str(row["payment_method"]).strip()
        )

        if payment_method is None:

            add_issue(
                "missing_payment_method",
                "payment_method",
                "Payment method is required.",
            )

        elif payment_method not in ALLOWED_PAYMENT_METHODS:

            add_issue(
                "unsupported_payment_method",
                "payment_method",
                f"Unsupported payment method: {payment_method}.",
            )

        # ---------------------------------------------------------
        # Payment status
        # ---------------------------------------------------------

        payment_status = (
            None
            if _is_blank(row["payment_status"])
            else str(row["payment_status"]).strip()
        )

        if payment_status is None:

            add_issue(
                "missing_payment_status",
                "payment_status",
                "Payment status is required.",
            )

        elif payment_status not in ALLOWED_PAYMENT_STATUSES:

            add_issue(
                "unsupported_payment_status",
                "payment_status",
                f"Unsupported payment status: {payment_status}.",
            )

        # ---------------------------------------------------------
        # Payment date
        # ---------------------------------------------------------

        raw_payment_date = row["payment_date"]

        if _is_blank(raw_payment_date):

            add_issue(
                "missing_payment_date",
                "payment_date",
                "Payment date is required.",
            )

        else:

            payment_date = _parse_date(raw_payment_date)

            if payment_date is None:

                add_issue(
                    "invalid_payment_date",
                    "payment_date",
                    "Payment date must use YYYY-MM-DD format "
                    "and contain a valid date.",
                )

            else:

                if payment_date > reference_date:

                    add_issue(
                        "future_payment_date",
                        "payment_date",
                        "Payment date cannot exceed the reference date.",
                    )

                if (
                    order_id is not None
                    and order_id in parsed_order_dates
                    and payment_date < parsed_order_dates[order_id]
                ):

                    add_issue(
                        "payment_before_order",
                        "payment_date",
                        "Payment date cannot be earlier than "
                        "the referenced order date.",
                    )

        # ---------------------------------------------------------
        # Payment amount
        # ---------------------------------------------------------

        payment_amount = _parse_decimal(
            row["payment_amount"]
        )

        if _is_blank(row["payment_amount"]):

            add_issue(
                "missing_payment_amount",
                "payment_amount",
                "Payment amount is required.",
            )

        elif payment_amount is None:

            add_issue(
                "invalid_payment_amount",
                "payment_amount",
                "Payment amount must be a finite numeric value.",
            )

        elif payment_amount <= 0:

            add_issue(
                "non_positive_payment_amount",
                "payment_amount",
                "Payment amount must be greater than zero.",
            )

        elif (
            order_id is not None
            and order_id in parsed_order_totals
            and payment_amount != parsed_order_totals[order_id]
        ):

            add_issue(
                "payment_amount_mismatch",
                "payment_amount",
                "Payment amount must equal the calculated net "
                "order total.",
            )

        if issues:
            issues_by_position[position] = issues

    return create_validation_result(
        dataframe,
        issues_by_position,
    )
