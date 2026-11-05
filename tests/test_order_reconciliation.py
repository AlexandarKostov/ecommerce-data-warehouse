"""Tests for cross-dataset order reconciliation."""

import pandas as pd
import pytest

from src.transformation.reconciliation import (
    ReconciliationResult,
    reconcile_orders,
)
from src.transformation.validation_result import (
    ValidationError,
    ValidationResult,
)


ORDER_COLUMNS = ["source_order_id", "order_status"]

ITEM_COLUMNS = [
    "source_order_item_id",
    "source_order_id",
    "quantity",
    "unit_price",
    "discount_amount",
]

PAYMENT_COLUMNS = [
    "source_payment_id",
    "source_order_id",
    "payment_status",
    "payment_amount",
]


def make_result(valid_rows, columns, rejected_rows=None):
    return ValidationResult(
        valid_records=pd.DataFrame(valid_rows, columns=columns),
        rejected_records=pd.DataFrame(
            rejected_rows or [],
            columns=columns + (["rejection_reasons"] if rejected_rows else []),
        ),
    )


def make_inputs(
    order_status="delivered",
    payment_statuses=None,
    include_items=True,
    include_payments=True,
    payment_amount="100.00",
    rejected_orders=None,
):
    if payment_statuses is None:
        payment_statuses = ["Completed"]

    orders = make_result(
        [{"source_order_id": "O1", "order_status": order_status}],
        ORDER_COLUMNS,
        rejected_orders,
    )

    items = []

    if include_items:
        items = [
            {
                "source_order_item_id": "I1",
                "source_order_id": "O1",
                "quantity": "2",
                "unit_price": "60.00",
                "discount_amount": "20.00",
            }
        ]

    order_items = make_result(items, ITEM_COLUMNS)

    payments = []

    if include_payments:
        payments = [
            {
                "source_payment_id": f"P{i + 1}",
                "source_order_id": "O1",
                "payment_status": status,
                "payment_amount": payment_amount,
            }
            for i, status in enumerate(payment_statuses)
        ]

    payment_result = make_result(payments, PAYMENT_COLUMNS)

    return orders, order_items, payment_result


def test_valid_delivered_order_reconciles():
    results = reconcile_orders(*make_inputs())

    assert isinstance(results, ReconciliationResult)
    assert len(results.valid_orders) == 1
    assert len(results.valid_order_items) == 1
    assert len(results.valid_payments) == 1
    assert results.rejected_count == 0


def test_failed_attempt_followed_by_completed_payment_is_valid():
    results = reconcile_orders(
        *make_inputs(payment_statuses=["Failed", "Completed"])
    )

    assert len(results.valid_orders) == 1
    assert len(results.valid_payments) == 2
    assert results.rejected_count == 0


def test_pending_order_requires_pending_payment():
    results = reconcile_orders(
        *make_inputs(
            order_status="pending",
            payment_statuses=["Completed"],
        )
    )

    assert len(results.valid_orders) == 0
    assert len(results.rejected_orders) == 1
    assert len(results.rejected_order_items) == 1
    assert len(results.rejected_payments) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "INCONSISTENT_PENDING_PAYMENT" in codes


def test_cancelled_order_requires_failed_payment():
    results = reconcile_orders(
        *make_inputs(
            order_status="cancelled",
            payment_statuses=["Completed"],
        )
    )

    assert len(results.rejected_orders) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "INCONSISTENT_CANCELLED_PAYMENT" in codes


def test_returned_order_requires_completed_and_refunded_payments():
    results = reconcile_orders(
        *make_inputs(
            order_status="returned",
            payment_statuses=["Completed"],
        )
    )

    assert len(results.rejected_orders) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "INCOMPLETE_RETURN_PAYMENT_HISTORY" in codes


def test_valid_returned_order_has_completed_and_refunded_payments():
    results = reconcile_orders(
        *make_inputs(
            order_status="returned",
            payment_statuses=["Completed", "Refunded"],
        )
    )

    assert len(results.valid_orders) == 1
    assert len(results.valid_payments) == 2
    assert results.rejected_count == 0


@pytest.mark.parametrize(
    "order_status",
    ["processing", "shipped", "delivered"],
)
def test_active_orders_require_completed_payment(order_status):
    results = reconcile_orders(
        *make_inputs(
            order_status=order_status,
            payment_statuses=["Failed"],
        )
    )

    assert len(results.rejected_orders) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "MISSING_COMPLETED_PAYMENT" in codes


def test_order_without_valid_items_is_rejected():
    results = reconcile_orders(
        *make_inputs(include_items=False)
    )

    assert len(results.rejected_orders) == 1
    assert len(results.rejected_payments) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "ORDER_WITHOUT_VALID_ITEMS" in codes


def test_order_without_valid_payments_is_rejected():
    results = reconcile_orders(
        *make_inputs(include_payments=False)
    )

    assert len(results.rejected_orders) == 1
    assert len(results.rejected_order_items) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "ORDER_WITHOUT_VALID_PAYMENTS" in codes


def test_payment_amount_must_match_recalculated_order_total():
    results = reconcile_orders(
        *make_inputs(payment_amount="99.99")
    )

    assert len(results.rejected_orders) == 1
    assert len(results.rejected_order_items) == 1
    assert len(results.rejected_payments) == 1

    codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[0]["rejection_reasons"]
    }

    assert "RECONCILIATION_PAYMENT_AMOUNT_MISMATCH" in codes


def test_rejected_parent_order_rejects_valid_child_records():
    rejected_order = {
        "source_order_id": "O1",
        "order_status": "delivered",
        "rejection_reasons": [
            {
                "code": "INVALID_ORDER",
                "field": "order_status",
                "message": "Previously rejected.",
            }
        ],
    }

    orders = make_result(
        [],
        ORDER_COLUMNS,
        [rejected_order],
    )

    items = make_result(
        [
            {
                "source_order_item_id": "I1",
                "source_order_id": "O1",
                "quantity": "2",
                "unit_price": "60.00",
                "discount_amount": "20.00",
            }
        ],
        ITEM_COLUMNS,
    )

    payments = make_result(
        [
            {
                "source_payment_id": "P1",
                "source_order_id": "O1",
                "payment_status": "Completed",
                "payment_amount": "100.00",
            }
        ],
        PAYMENT_COLUMNS,
    )

    results = reconcile_orders(orders, items, payments)

    assert len(results.valid_orders) == 0
    assert len(results.valid_order_items) == 0
    assert len(results.valid_payments) == 0

    assert len(results.rejected_orders) == 1
    assert len(results.rejected_order_items) == 1
    assert len(results.rejected_payments) == 1


def test_rejected_duplicate_does_not_invalidate_valid_canonical_order():
    rejected_duplicate = {
        "source_order_id": "O1",
        "order_status": "delivered",
        "rejection_reasons": [
            {
                "code": "DUPLICATE_SOURCE_ORDER_ID",
                "field": "source_order_id",
                "message": "Duplicate order ID.",
            }
        ],
    }

    orders, items, payments = make_inputs(
        rejected_orders=[rejected_duplicate]
    )

    results = reconcile_orders(orders, items, payments)

    assert len(results.valid_orders) == 1
    assert len(results.valid_order_items) == 1
    assert len(results.valid_payments) == 1

    assert len(results.rejected_orders) == 1
    assert len(results.rejected_order_items) == 0
    assert len(results.rejected_payments) == 0

    assert (
        results.rejected_orders.iloc[0]["rejection_reasons"][0]["code"]
        == "DUPLICATE_SOURCE_ORDER_ID"
    )


def test_valid_canonical_order_rejected_during_reconciliation_rejects_children():
    rejected_duplicate = {
        "source_order_id": "O1",
        "order_status": "delivered",
        "rejection_reasons": [
            {
                "code": "DUPLICATE_SOURCE_ORDER_ID",
                "field": "source_order_id",
                "message": "Duplicate order ID.",
            }
        ],
    }

    orders, items, payments = make_inputs(
        payment_statuses=["Failed"],
        rejected_orders=[rejected_duplicate],
    )

    results = reconcile_orders(orders, items, payments)

    assert len(results.valid_orders) == 0
    assert len(results.valid_order_items) == 0
    assert len(results.valid_payments) == 0

    assert len(results.rejected_orders) == 2
    assert len(results.rejected_order_items) == 1
    assert len(results.rejected_payments) == 1

    rejection_codes = {
        issue["code"]
        for issue in results.rejected_orders.iloc[1]["rejection_reasons"]
    }

    assert "MISSING_COMPLETED_PAYMENT" in rejection_codes


def test_existing_rejections_are_preserved():
    rejected_order = {
        "source_order_id": "O2",
        "order_status": "pending",
        "rejection_reasons": [
            {
                "code": "INVALID_ORDER",
                "field": "order_status",
                "message": "Previously rejected.",
            }
        ],
    }

    orders, items, payments = make_inputs(
        rejected_orders=[rejected_order]
    )

    results = reconcile_orders(orders, items, payments)

    assert len(results.rejected_orders) == 1

    reasons = results.rejected_orders.iloc[0]["rejection_reasons"]

    assert reasons[0]["code"] == "INVALID_ORDER"


def test_reconciliation_does_not_modify_input_dataframes():
    orders, items, payments = make_inputs()

    original_orders = orders.valid_records.copy(deep=True)
    original_items = items.valid_records.copy(deep=True)
    original_payments = payments.valid_records.copy(deep=True)

    reconcile_orders(orders, items, payments)

    pd.testing.assert_frame_equal(
        orders.valid_records,
        original_orders,
    )

    pd.testing.assert_frame_equal(
        items.valid_records,
        original_items,
    )

    pd.testing.assert_frame_equal(
        payments.valid_records,
        original_payments,
    )


def test_reconciliation_result_counts_rejected_records_and_issues():
    results = reconcile_orders(
        *make_inputs(
            order_status="pending",
            payment_statuses=["Completed"],
        )
    )

    assert results.rejected_count == 3
    assert results.issue_count == 3


def test_invalid_input_type_raises_validation_error():
    with pytest.raises(ValidationError):
        reconcile_orders(
            pd.DataFrame(),
            make_result([], ITEM_COLUMNS),
            make_result([], PAYMENT_COLUMNS),
        )