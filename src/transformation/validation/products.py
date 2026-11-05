"""
Product dataset validation.

Validates product identifiers, names, financial values,
stock quantities, and duplicate source product IDs.

The validator is pure: it does not modify input data or access
the database.
"""

import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    ValidationResult,
    create_validation_result,
)


REQUIRED_COLUMNS = {
    "source_product_id",
    "product_name",
    "unit_price",
    "unit_cost",
    "stock_quantity",
}

INTEGER_PATTERN = re.compile(r"^\d+(?:\.0+)?$")


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


def _parse_decimal(value: object) -> Decimal | None:
    """Parse a value as Decimal without using floating-point arithmetic."""

    if _is_blank(value):
        return None

    try:
        parsed_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not parsed_value.is_finite():
        return None

    return parsed_value


def _is_valid_non_negative_decimal(value: object) -> bool:
    """Check whether a value is a finite, non-negative decimal."""

    parsed_value = _parse_decimal(value)

    return (
        parsed_value is not None
        and parsed_value >= Decimal("0")
    )


def _is_valid_stock_quantity(value: object) -> bool:
    """Check whether stock quantity is a non-negative whole number."""

    if _is_blank(value):
        return False

    normalized_value = str(value).strip()

    if not INTEGER_PATTERN.fullmatch(normalized_value):
        return False

    parsed_value = _parse_decimal(normalized_value)

    return (
        parsed_value is not None
        and parsed_value >= Decimal("0")
        and parsed_value == parsed_value.to_integral_value()
    )


def validate_products(
    dataframe: pd.DataFrame,
) -> ValidationResult:
    """
    Validate a product dataset.

    Rules:
        - source_product_id must be present.
        - product_name must be present.
        - unit_price must be numeric, finite, and non-negative.
        - unit_cost may be blank; when supplied, it must be
          numeric, finite, and non-negative.
        - stock_quantity must be a non-negative whole number.
        - source_product_id must be unique within the dataset.

    Duplicate handling:
        The first occurrence of a non-empty source product ID
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
            "Product validation input must be a pandas DataFrame."
        )

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise ValidationError(
            "Product dataset is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    issues_by_position: dict[int, list[ValidationIssue]] = {}
    seen_product_ids: set[str] = set()

    for position in range(len(dataframe)):
        record = dataframe.iloc[position]
        issues: list[ValidationIssue] = []

        product_id = record["source_product_id"]
        product_name = record["product_name"]
        unit_price = record["unit_price"]
        unit_cost = record["unit_cost"]
        stock_quantity = record["stock_quantity"]

        # Validate the source product identifier.
        if _is_blank(product_id):
            issues.append(
                ValidationIssue(
                    code="MISSING_PRODUCT_ID",
                    field="source_product_id",
                    message="Product ID is required.",
                )
            )
        else:
            normalized_id = str(product_id).strip()

            if normalized_id in seen_product_ids:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_PRODUCT_ID",
                        field="source_product_id",
                        message=(
                            "Product ID already exists in this dataset. "
                            "The first occurrence is retained."
                        ),
                    )
                )
            else:
                seen_product_ids.add(normalized_id)

        # Validate the product name.
        if _is_blank(product_name):
            issues.append(
                ValidationIssue(
                    code="MISSING_PRODUCT_NAME",
                    field="product_name",
                    message="Product name is required.",
                )
            )

        # Validate the selling price.
        if _is_blank(unit_price):
            issues.append(
                ValidationIssue(
                    code="MISSING_UNIT_PRICE",
                    field="unit_price",
                    message="Unit price is required.",
                )
            )
        elif not _is_valid_non_negative_decimal(unit_price):
            issues.append(
                ValidationIssue(
                    code="INVALID_UNIT_PRICE",
                    field="unit_price",
                    message=(
                        "Unit price must be a finite, "
                        "non-negative numeric value."
                    ),
                )
            )

        # Unit cost is nullable in dim_products.
        # A supplied value must still be valid.
        if not _is_blank(unit_cost):
            if not _is_valid_non_negative_decimal(unit_cost):
                issues.append(
                    ValidationIssue(
                        code="INVALID_UNIT_COST",
                        field="unit_cost",
                        message=(
                            "Unit cost must be a finite, "
                            "non-negative numeric value when supplied."
                        ),
                    )
                )

        # Validate stock quantity.
        if _is_blank(stock_quantity):
            issues.append(
                ValidationIssue(
                    code="MISSING_STOCK_QUANTITY",
                    field="stock_quantity",
                    message="Stock quantity is required.",
                )
            )
        elif not _is_valid_stock_quantity(stock_quantity):
            issues.append(
                ValidationIssue(
                    code="INVALID_STOCK_QUANTITY",
                    field="stock_quantity",
                    message=(
                        "Stock quantity must be a non-negative "
                        "whole number."
                    ),
                )
            )

        if issues:
            issues_by_position[position] = issues

    return create_validation_result(
        dataframe=dataframe,
        issues_by_position=issues_by_position,
    )