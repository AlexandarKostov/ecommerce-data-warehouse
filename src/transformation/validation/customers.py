
"""
Customer dataset validation.

Validates required customer identifiers, email addresses,
and duplicate source customer IDs.

The validator is pure: it does not modify input data or access
the database.
"""

import re

import pandas as pd

from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    ValidationResult,
    create_validation_result,
)


REQUIRED_COLUMNS = {
    "source_customer_id",
    "email",
}

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


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


def _is_valid_email(value: object) -> bool:
    """Perform basic email syntax validation."""

    if not isinstance(value, str):
        return False

    normalized_email = value.strip()

    return bool(EMAIL_PATTERN.fullmatch(normalized_email))


def validate_customers(
    dataframe: pd.DataFrame,
) -> ValidationResult:
    """
    Validate a customer dataset.

    Rules:
        - source_customer_id must be present.
        - email must be present.
        - email must have a plausible email format.
        - source_customer_id must be unique within the dataset.

    Duplicate handling:
        The first occurrence of a non-empty source customer ID
        is retained. Subsequent occurrences are rejected.

        Duplicate comparison ignores leading and trailing
        whitespace but remains case-sensitive.

    Returns:
        ValidationResult containing valid and rejected records.

    Raises:
        ValidationError: If the input is not a DataFrame or
                         required columns are missing.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise ValidationError(
            "Customer validation input must be a pandas DataFrame."
        )

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise ValidationError(
            "Customer dataset is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    issues_by_position: dict[int, list[ValidationIssue]] = {}
    seen_customer_ids: set[str] = set()

    for position in range(len(dataframe)):
        record = dataframe.iloc[position]
        issues: list[ValidationIssue] = []

        customer_id = record["source_customer_id"]
        email = record["email"]

        # Validate the source customer identifier.
        if _is_blank(customer_id):
            issues.append(
                ValidationIssue(
                    code="MISSING_CUSTOMER_ID",
                    field="source_customer_id",
                    message="Customer ID is required.",
                )
            )
        else:
            normalized_id = str(customer_id).strip()

            if normalized_id in seen_customer_ids:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_CUSTOMER_ID",
                        field="source_customer_id",
                        message=(
                            "Customer ID already exists in this "
                            "dataset. The first occurrence is retained."
                        ),
                    )
                )
            else:
                seen_customer_ids.add(normalized_id)

        # Validate the email address.
        if _is_blank(email):
            issues.append(
                ValidationIssue(
                    code="MISSING_EMAIL",
                    field="email",
                    message="Customer email is required.",
                )
            )
        elif not _is_valid_email(email):
            issues.append(
                ValidationIssue(
                    code="INVALID_EMAIL",
                    field="email",
                    message="Customer email has an invalid format.",
                )
            )

        if issues:
            issues_by_position[position] = issues

    return create_validation_result(
        dataframe=dataframe,
        issues_by_position=issues_by_position,
    )
