"""
Order-item data validation.

Validates order-item records before they enter the warehouse
transformation layer.

Validation includes:
- Required and unique source identifiers.
- Referential integrity against valid orders and products.
- Positive whole-number quantities.
- Valid financial values using Decimal.
- Discounts that do not exceed gross line revenue.

The original DataFrame is never modified.
"""

from collections.abc import Set
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    ValidationResult,
    create_validation_result,
)


REQUIRED_COLUMNS = {
    "source_order_item_id",
    "source_order_id",
    "source_product_id",
    "quantity",
    "unit_price",
    "discount_amount",
}


def _is_missing(value) -> bool:
    """Safely determine whether a value is missing."""

    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_blank(value) -> bool:
    """Check whether a value is missing or contains only whitespace."""

    if _is_missing(value):
        return True

    return isinstance(value, str) and not value.strip()


def _normalize_identifier(value) -> str:
    """Normalize an identifier without changing its case."""

    return str(value).strip()


def _parse_decimal(value) -> Decimal | None:
    """
    Parse a finite Decimal value.

    Returns None when the value is missing, invalid,
    or not finite.
    """

    if _is_blank(value):
        return None

    try:
        parsed_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not parsed_value.is_finite():
        return None

    return parsed_value


def _parse_quantity(value) -> Decimal | None:
    """
    Parse a positive whole-number quantity.

    Decimal is used to avoid accepting fractional quantities
    or introducing floating-point precision issues.
    """

    quantity = _parse_decimal(value)

    if quantity is None:
        return None

    if quantity <= 0:
        return None

    if quantity != quantity.to_integral_value():
        return None

    return quantity


def validate_order_items(
    dataframe: pd.DataFrame,
    valid_order_ids: Set[str],
    valid_product_ids: Set[str],
) -> ValidationResult:
    """
    Validate order-item records.

    Parameters
    ----------
    dataframe:
        Extracted order-item staging records.

    valid_order_ids:
        Set of source order IDs that passed order validation.

    valid_product_ids:
        Set of source product IDs that passed product validation.

    Returns
    -------
    ValidationResult
        Contains valid records, rejected records, and
        structured validation issues.

    Notes
    -----
    - The first occurrence of an order-item ID is canonical.
    - Duplicate IDs are rejected even if the first occurrence
      has other validation errors.
    - References are checked against valid records, not merely
      records present in staging.
    - Original records are never modified.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise ValidationError(
            "Order items must be provided as a pandas DataFrame."
        )

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise ValidationError(
            "Order items DataFrame is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if not isinstance(valid_order_ids, Set):
        raise ValidationError(
            "valid_order_ids must be a set or frozenset."
        )

    if not isinstance(valid_product_ids, Set):
        raise ValidationError(
            "valid_product_ids must be a set or frozenset."
        )

    normalized_order_ids = {
        _normalize_identifier(value)
        for value in valid_order_ids
        if not _is_blank(value)
    }

    normalized_product_ids = {
        _normalize_identifier(value)
        for value in valid_product_ids
        if not _is_blank(value)
    }

    issues_by_position = {}
    seen_order_item_ids = set()

    for position, (_, row) in enumerate(dataframe.iterrows()):

        row_issues = []

        # ----------------------------------------------------
        # 1. Validate order-item identifier
        # ----------------------------------------------------

        item_id = row["source_order_item_id"]

        if _is_blank(item_id):

            row_issues.append(
                ValidationIssue(
                    code="missing_order_item_id",
                    field="source_order_item_id",
                    message="Order-item ID is required.",
                )
            )

        else:

            normalized_item_id = _normalize_identifier(item_id)

            if normalized_item_id in seen_order_item_ids:

                row_issues.append(
                    ValidationIssue(
                        code="duplicate_order_item_id",
                        field="source_order_item_id",
                        message="Order-item ID must be unique.",
                    )
                )

            else:
                # The first occurrence remains canonical,
                # even if it has other validation issues.
                seen_order_item_ids.add(normalized_item_id)

        # ----------------------------------------------------
        # 2. Validate order reference
        # ----------------------------------------------------

        order_id = row["source_order_id"]

        if _is_blank(order_id):

            row_issues.append(
                ValidationIssue(
                    code="missing_order_reference",
                    field="source_order_id",
                    message="Order reference is required.",
                )
            )

        elif (
            _normalize_identifier(order_id)
            not in normalized_order_ids
        ):

            row_issues.append(
                ValidationIssue(
                    code="invalid_order_reference",
                    field="source_order_id",
                    message="Order reference does not match a valid order.",
                )
            )

        # ----------------------------------------------------
        # 3. Validate product reference
        # ----------------------------------------------------

        product_id = row["source_product_id"]

        if _is_blank(product_id):

            row_issues.append(
                ValidationIssue(
                    code="missing_product_reference",
                    field="source_product_id",
                    message="Product reference is required.",
                )
            )

        elif (
            _normalize_identifier(product_id)
            not in normalized_product_ids
        ):

            row_issues.append(
                ValidationIssue(
                    code="invalid_product_reference",
                    field="source_product_id",
                    message="Product reference does not match a valid product.",
                )
            )

        # ----------------------------------------------------
        # 4. Validate quantity
        # ----------------------------------------------------

        quantity = _parse_quantity(row["quantity"])

        if quantity is None:

            row_issues.append(
                ValidationIssue(
                    code="invalid_quantity",
                    field="quantity",
                    message="Quantity must be a positive whole number.",
                )
            )

        # ----------------------------------------------------
        # 5. Validate unit price
        # ----------------------------------------------------

        unit_price = _parse_decimal(row["unit_price"])

        if unit_price is None or unit_price <= 0:

            row_issues.append(
                ValidationIssue(
                    code="invalid_unit_price",
                    field="unit_price",
                    message="Unit price must be a finite number greater than zero.",
                )
            )

        # ----------------------------------------------------
        # 6. Validate discount amount
        # ----------------------------------------------------

        discount_amount = _parse_decimal(row["discount_amount"])

        if discount_amount is None or discount_amount < 0:

            row_issues.append(
                ValidationIssue(
                    code="invalid_discount_amount",
                    field="discount_amount",
                    message="Discount must be a finite number equal to or greater than zero.",
                )
            )

        # ----------------------------------------------------
        # 7. Validate discount against gross line revenue
        # ----------------------------------------------------

        if (
            quantity is not None
            and unit_price is not None
            and unit_price > 0
            and discount_amount is not None
            and discount_amount >= 0
        ):

            gross_revenue = quantity * unit_price

            if discount_amount > gross_revenue:

                row_issues.append(
                    ValidationIssue(
                        code="discount_exceeds_gross_revenue",
                        field="discount_amount",
                        message="Discount cannot exceed gross line revenue.",
                    )
                )

        # ----------------------------------------------------
        # Collect all issues for this physical record
        # ----------------------------------------------------

        if row_issues:
            issues_by_position[position] = row_issues

    return create_validation_result(
        dataframe,
        issues_by_position,
    )