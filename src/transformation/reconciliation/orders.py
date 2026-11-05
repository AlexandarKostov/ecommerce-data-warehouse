"""
Cross-dataset order reconciliation.

Reconciles individually validated orders, order items, and payments.

The reconciliation layer checks:
- Every accepted order has at least one valid order item.
- Every accepted order has at least one valid payment.
- Payment statuses are consistent with the order status.
- Payment amounts agree with independently calculated net order totals.
- Valid child records belonging to rejected orders are also rejected.

This module is pure:
- It does not modify input ValidationResult objects.
- It does not access the database.
- It does not write rejected records.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.transformation.validation_result import (
    ValidationError,
    ValidationResult,
)


@dataclass
class ReconciliationResult:
    """Consolidated valid and rejected records from reconciliation."""

    valid_orders: pd.DataFrame
    rejected_orders: pd.DataFrame

    valid_order_items: pd.DataFrame
    rejected_order_items: pd.DataFrame

    valid_payments: pd.DataFrame
    rejected_payments: pd.DataFrame

    @property
    def rejected_count(self) -> int:
        """Number of rejected physical records across all datasets."""

        return (
            len(self.rejected_orders)
            + len(self.rejected_order_items)
            + len(self.rejected_payments)
        )

    @property
    def issue_count(self) -> int:
        """Number of individual rejection reasons across all datasets."""

        total = 0

        for dataframe in (
            self.rejected_orders,
            self.rejected_order_items,
            self.rejected_payments,
        ):
            if (
                not dataframe.empty
                and "rejection_reasons" in dataframe.columns
            ):
                total += sum(
                    len(reasons)
                    for reasons in dataframe["rejection_reasons"]
                )

        return total


def _normalize_identifier(value) -> str | None:
    """Normalize identifiers without changing their case."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip()

    return normalized or None


def _parse_decimal(value) -> Decimal:
    """Parse a finite Decimal or raise a reconciliation error."""

    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(
            f"Cannot reconcile invalid financial value: {value!r}."
        ) from error

    if not amount.is_finite():
        raise ValidationError(
            f"Cannot reconcile non-finite financial value: {value!r}."
        )

    return amount


def _validate_inputs(
    orders: ValidationResult,
    order_items: ValidationResult,
    payments: ValidationResult,
) -> None:
    """Validate reconciliation inputs and required columns."""

    datasets = {
        "orders": (
            orders,
            {"source_order_id", "order_status"},
        ),
        "order_items": (
            order_items,
            {
                "source_order_id",
                "quantity",
                "unit_price",
                "discount_amount",
            },
        ),
        "payments": (
            payments,
            {"source_order_id", "payment_status", "payment_amount"},
        ),
    }

    for dataset_name, (result, required_columns) in datasets.items():

        if not isinstance(result, ValidationResult):
            raise ValidationError(
                f"{dataset_name} must be a ValidationResult."
            )

        for dataframe_name, dataframe in (
            ("valid_records", result.valid_records),
            ("rejected_records", result.rejected_records),
        ):
            if not isinstance(dataframe, pd.DataFrame):
                raise ValidationError(
                    f"{dataset_name}.{dataframe_name} must be a DataFrame."
                )

        missing_columns = (
            required_columns - set(result.valid_records.columns)
        )

        if missing_columns:
            raise ValidationError(
                f"{dataset_name} is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        missing_rejection_columns = (
            required_columns - set(result.rejected_records.columns)
        )

        if missing_rejection_columns:
            raise ValidationError(
                f"{dataset_name}.rejected_records is missing required "
                "source columns: "
                + ", ".join(sorted(missing_rejection_columns))
            )


def _index_by_order_id(
    dataframe: pd.DataFrame,
) -> dict[str, list[int]]:
    """Build an order ID to physical row-position mapping."""

    positions = defaultdict(list)

    for position in range(len(dataframe)):
        order_id = _normalize_identifier(
            dataframe.iloc[position]["source_order_id"]
        )

        if order_id is not None:
            positions[order_id].append(position)

    return dict(positions)


def _calculate_order_total(
    order_item_rows: pd.DataFrame,
) -> Decimal:
    """Calculate an order's net total using validated order items."""

    total = Decimal("0")

    for _, row in order_item_rows.iterrows():

        quantity = _parse_decimal(row["quantity"])
        unit_price = _parse_decimal(row["unit_price"])
        discount = _parse_decimal(row["discount_amount"])

        total += quantity * unit_price - discount

    return total


def _merge_rejections(
    original_rejections: pd.DataFrame,
    newly_rejected: pd.DataFrame,
) -> pd.DataFrame:
    """Combine original validation rejections and reconciliation rejections."""

    if original_rejections.empty and newly_rejected.empty:
        return original_rejections.copy()

    frames = []

    if not original_rejections.empty:
        frames.append(original_rejections.copy())

    if not newly_rejected.empty:
        frames.append(newly_rejected.copy())

    return pd.concat(frames, ignore_index=True)


def _build_rejected_records(
    dataframe: pd.DataFrame,
    issues_by_position: dict[int, list[dict[str, str]]],
) -> pd.DataFrame:
    """Create rejected records with structured rejection reasons."""

    if not issues_by_position:
        return dataframe.iloc[0:0].copy()

    positions = sorted(issues_by_position)

    rejected = dataframe.iloc[positions].copy()

    rejected["rejection_reasons"] = [
        issues_by_position[position]
        for position in positions
    ]

    return rejected


def _create_issue(
    code: str,
    field: str,
    message: str,
) -> dict[str, str]:
    """Create a serializable reconciliation issue."""

    return {
        "code": code,
        "field": field,
        "message": message,
    }


def _validate_payment_statuses(
    order_status: str,
    payment_statuses: set[str],
) -> list[dict[str, str]]:
    """Check payment history against the corresponding order status."""

    issues = []

    if order_status == "pending":

        if payment_statuses != {"pending"}:
            issues.append(
                _create_issue(
                    "INCONSISTENT_PENDING_PAYMENT",
                    "payment_status",
                    "Pending orders must have Pending payment transactions only.",
                )
            )

    elif order_status == "cancelled":

        if payment_statuses != {"failed"}:
            issues.append(
                _create_issue(
                    "INCONSISTENT_CANCELLED_PAYMENT",
                    "payment_status",
                    "Cancelled orders must have Failed payment transactions only.",
                )
            )

    elif order_status == "returned":

        if not {"completed", "refunded"}.issubset(payment_statuses):
            issues.append(
                _create_issue(
                    "INCOMPLETE_RETURN_PAYMENT_HISTORY",
                    "payment_status",
                    "Returned orders must have both Completed and Refunded transactions.",
                )
            )

        if payment_statuses - {"completed", "refunded"}:
            issues.append(
                _create_issue(
                    "UNEXPECTED_RETURN_PAYMENT_STATUS",
                    "payment_status",
                    "Returned orders cannot have Pending or Failed transactions.",
                )
            )

    elif order_status in {"processing", "shipped", "delivered"}:

        if "completed" not in payment_statuses:
            issues.append(
                _create_issue(
                    "MISSING_COMPLETED_PAYMENT",
                    "payment_status",
                    "Processing, shipped, and delivered orders must have a Completed payment.",
                )
            )

        if payment_statuses - {"completed", "failed"}:
            issues.append(
                _create_issue(
                    "UNEXPECTED_PAYMENT_STATUS",
                    "payment_status",
                    "These orders may only have Failed attempts and Completed payments.",
                )
            )

    return issues


def reconcile_orders(
    orders: ValidationResult,
    order_items: ValidationResult,
    payments: ValidationResult,
) -> ReconciliationResult:
    """
    Reconcile individually validated orders, order items, and payments.

    The function does not modify its input ValidationResult objects.

    An order rejected during reconciliation causes its otherwise-valid
    order items and payments to be rejected as dependent records.

    Existing individual validation rejections are preserved.

    A rejected duplicate order does not invalidate child records belonging
    to an accepted canonical order with the same source order ID.
    """

    _validate_inputs(orders, order_items, payments)

    valid_orders = orders.valid_records
    valid_items = order_items.valid_records
    valid_payments = payments.valid_records

    item_positions = _index_by_order_id(valid_items)
    payment_positions = _index_by_order_id(valid_payments)

    order_issues: dict[int, list[dict[str, str]]] = {}

    # ---------------------------------------------------------
    # Identify accepted canonical orders.
    #
    # A source order ID can appear in rejected_records because
    # a later duplicate occurrence was rejected.
    #
    # If that ID also exists in valid_records, the accepted
    # canonical order takes precedence.
    # ---------------------------------------------------------

    valid_order_ids = {
        order_id
        for order_id in (
            _normalize_identifier(value)
            for value in valid_orders["source_order_id"]
        )
        if order_id is not None
    }

    rejected_order_ids = {
        order_id
        for order_id in (
            _normalize_identifier(value)
            for value in orders.rejected_records["source_order_id"]
        )
        if order_id is not None
    } - valid_order_ids

    # ---------------------------------------------------------
    # Reconcile each individually valid order.
    # ---------------------------------------------------------

    for position in range(len(valid_orders)):

        order = valid_orders.iloc[position]

        order_id = _normalize_identifier(order["source_order_id"])
        order_status = str(order["order_status"]).strip().casefold()

        issues = []

        current_item_positions = item_positions.get(order_id, [])
        current_payment_positions = payment_positions.get(order_id, [])

        if not current_item_positions:

            issues.append(
                _create_issue(
                    "ORDER_WITHOUT_VALID_ITEMS",
                    "source_order_id",
                    "Order has no valid order-item records.",
                )
            )

        if not current_payment_positions:

            issues.append(
                _create_issue(
                    "ORDER_WITHOUT_VALID_PAYMENTS",
                    "source_order_id",
                    "Order has no valid payment transactions.",
                )
            )

        # -----------------------------------------------------
        # Check payment history against the order status.
        # -----------------------------------------------------

        if current_payment_positions:

            payment_statuses = {
                str(
                    valid_payments.iloc[p]["payment_status"]
                ).strip().casefold()
                for p in current_payment_positions
            }

            issues.extend(
                _validate_payment_statuses(
                    order_status,
                    payment_statuses,
                )
            )

        # -----------------------------------------------------
        # Independently reconcile payment amounts against
        # the calculated net order total.
        # -----------------------------------------------------

        if current_item_positions and current_payment_positions:

            item_rows = valid_items.iloc[current_item_positions]

            calculated_total = _calculate_order_total(item_rows)

            if calculated_total <= 0:

                issues.append(
                    _create_issue(
                        "NON_POSITIVE_RECONCILED_ORDER_TOTAL",
                        "source_order_id",
                        "Calculated net order total must be greater than zero.",
                    )
                )

            else:

                for payment_position in current_payment_positions:

                    payment = valid_payments.iloc[payment_position]

                    payment_amount = _parse_decimal(
                        payment["payment_amount"]
                    )

                    if payment_amount != calculated_total:

                        issues.append(
                            _create_issue(
                                "RECONCILIATION_PAYMENT_AMOUNT_MISMATCH",
                                "payment_amount",
                                (
                                    "Payment amount does not match the "
                                    "independently calculated net order total."
                                ),
                            )
                        )

                        break

        if issues:
            order_issues[position] = issues
            rejected_order_ids.add(order_id)

    # ---------------------------------------------------------
    # Build rejected order records.
    # ---------------------------------------------------------

    newly_rejected_orders = _build_rejected_records(
        valid_orders,
        order_issues,
    )

    # ---------------------------------------------------------
    # Reject valid child records belonging to rejected orders.
    #
    # This includes:
    # - Orders rejected by individual validation with no
    #   accepted canonical order.
    # - Orders that failed cross-dataset reconciliation.
    #
    # It excludes rejected duplicate occurrences when their
    # canonical order was accepted and reconciled successfully.
    # ---------------------------------------------------------

    item_issues = {}
    payment_issues = {}

    for position in range(len(valid_items)):

        order_id = _normalize_identifier(
            valid_items.iloc[position]["source_order_id"]
        )

        if order_id in rejected_order_ids:

            item_issues[position] = [
                _create_issue(
                    "PARENT_ORDER_REJECTED",
                    "source_order_id",
                    "Order item belongs to an order that failed validation or reconciliation.",
                )
            ]

    for position in range(len(valid_payments)):

        order_id = _normalize_identifier(
            valid_payments.iloc[position]["source_order_id"]
        )

        if order_id in rejected_order_ids:

            payment_issues[position] = [
                _create_issue(
                    "PARENT_ORDER_REJECTED",
                    "source_order_id",
                    "Payment belongs to an order that failed validation or reconciliation.",
                )
            ]

    newly_rejected_items = _build_rejected_records(
        valid_items,
        item_issues,
    )

    newly_rejected_payments = _build_rejected_records(
        valid_payments,
        payment_issues,
    )

    # ---------------------------------------------------------
    # Determine the final valid records.
    # ---------------------------------------------------------

    final_valid_orders = valid_orders.iloc[
        [
            position
            for position in range(len(valid_orders))
            if position not in order_issues
        ]
    ].copy()

    final_valid_items = valid_items.iloc[
        [
            position
            for position in range(len(valid_items))
            if position not in item_issues
        ]
    ].copy()

    final_valid_payments = valid_payments.iloc[
        [
            position
            for position in range(len(valid_payments))
            if position not in payment_issues
        ]
    ].copy()

    return ReconciliationResult(
        valid_orders=final_valid_orders,
        rejected_orders=_merge_rejections(
            orders.rejected_records,
            newly_rejected_orders,
        ),
        valid_order_items=final_valid_items,
        rejected_order_items=_merge_rejections(
            order_items.rejected_records,
            newly_rejected_items,
        ),
        valid_payments=final_valid_payments,
        rejected_payments=_merge_rejections(
            payments.rejected_records,
            newly_rejected_payments,
        ),
    )