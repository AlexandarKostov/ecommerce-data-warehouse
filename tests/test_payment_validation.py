
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from src.transformation.validation.payments import (
    ALLOWED_PAYMENT_METHODS,
    ALLOWED_PAYMENT_STATUSES,
    validate_payments,
)
from src.transformation.validation_result import ValidationError


@pytest.fixture
def reference_data():
    return {
        "valid_order_ids": {
            "ORD001",
            "ORD002",
            "ORD003",
        },
        "valid_order_dates": {
            "ORD001": "2026-10-01",
            "ORD002": "2026-10-10",
            "ORD003": "2026-10-15",
        },
        "expected_order_totals": {
            "ORD001": Decimal("100.00"),
            "ORD002": Decimal("250.50"),
            "ORD003": Decimal("75.25"),
        },
    }


@pytest.fixture
def payments():
    return pd.DataFrame(
        [
            {
                "source_payment_id": "PAY001",
                "source_order_id": "ORD001",
                "payment_method": "Credit Card",
                "payment_status": "Completed",
                "payment_date": "2026-10-02",
                "payment_amount": "100.00",
            },
            {
                "source_payment_id": "PAY002",
                "source_order_id": "ORD002",
                "payment_method": "PayPal",
                "payment_status": "Failed",
                "payment_date": "2026-10-11",
                "payment_amount": "250.50",
            },
            {
                "source_payment_id": "PAY003",
                "source_order_id": "ORD003",
                "payment_method": "Bank Transfer",
                "payment_status": "Pending",
                "payment_date": "2026-10-16",
                "payment_amount": "75.25",
            },
        ]
    )


def run_validation(dataframe, reference_data):
    return validate_payments(
        dataframe=dataframe,
        **reference_data,
    )


def rejection_codes(row):
    return {
        issue["code"]
        for issue in row["rejection_reasons"]
    }


# ---------------------------------------------------------------------
# Valid payment records
# ---------------------------------------------------------------------


def test_valid_payments_are_accepted(payments, reference_data):
    result = run_validation(payments, reference_data)

    assert result.valid_count == 3
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_all_supported_payment_statuses_are_valid(
    payments,
    reference_data,
):
    statuses = list(ALLOWED_PAYMENT_STATUSES)

    dataframe = pd.concat(
        [
            payments.iloc[[0]].copy()
            for _ in statuses
        ],
        ignore_index=True,
    )

    dataframe["source_payment_id"] = [
        f"PAY{i:03d}"
        for i in range(1, len(statuses) + 1)
    ]

    dataframe["payment_status"] = statuses

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == len(statuses)
    assert result.rejected_count == 0


def test_all_supported_payment_methods_are_valid(
    payments,
    reference_data,
):
    methods = list(ALLOWED_PAYMENT_METHODS)

    dataframe = pd.concat(
        [
            payments.iloc[[0]].copy()
            for _ in methods
        ],
        ignore_index=True,
    )

    dataframe["source_payment_id"] = [
        f"PAY{i:03d}"
        for i in range(1, len(methods) + 1)
    ]

    dataframe["payment_method"] = methods

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == len(methods)
    assert result.rejected_count == 0


def test_refunded_payment_uses_positive_order_total(
    payments,
    reference_data,
):
    dataframe = payments.iloc[[0]].copy()

    dataframe.loc[
        dataframe.index[0],
        "payment_status",
    ] = "Refunded"

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == 1
    assert result.rejected_count == 0


def test_payment_amount_accepts_decimal_precision(
    payments,
    reference_data,
):
    dataframe = payments.iloc[[0]].copy()

    # Allow Python Decimal objects in this column.
    dataframe["payment_amount"] = (
        dataframe["payment_amount"].astype(object)
    )

    dataframe.loc[
        dataframe.index[0],
        "payment_amount",
    ] = Decimal("100.00")

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == 1
    assert result.rejected_count == 0

# ---------------------------------------------------------------------
# Required columns and reference data
# ---------------------------------------------------------------------


def test_non_dataframe_input_raises_validation_error(
    reference_data,
):
    with pytest.raises(
        ValidationError,
        match="pandas DataFrame",
    ):
        validate_payments(
            [],
            **reference_data,
        )


def test_missing_required_column_raises_validation_error(
    payments,
    reference_data,
):
    dataframe = payments.drop(
        columns=["payment_amount"]
    )

    with pytest.raises(
        ValidationError,
        match="missing columns",
    ):
        run_validation(dataframe, reference_data)


@pytest.mark.parametrize(
    "invalid_order_ids",
    [
        ["ORD001", "ORD002"],
        "ORD001",
        None,
    ],
)
def test_invalid_order_id_collection_raises_error(
    payments,
    reference_data,
    invalid_order_ids,
):
    with pytest.raises(
        ValidationError,
        match="set or frozenset",
    ):
        validate_payments(
            dataframe=payments,
            valid_order_ids=invalid_order_ids,
            valid_order_dates=reference_data["valid_order_dates"],
            expected_order_totals=reference_data["expected_order_totals"],
        )


def test_order_dates_must_cover_all_valid_orders(
    payments,
    reference_data,
):
    reference_data["valid_order_dates"].pop("ORD003")

    with pytest.raises(
        ValidationError,
        match="does not contain dates",
    ):
        run_validation(payments, reference_data)


def test_order_totals_must_cover_all_valid_orders(
    payments,
    reference_data,
):
    reference_data["expected_order_totals"].pop("ORD003")

    with pytest.raises(
        ValidationError,
        match="does not contain totals",
    ):
        run_validation(payments, reference_data)


def test_invalid_reference_order_date_raises_error(
    payments,
    reference_data,
):
    reference_data["valid_order_dates"]["ORD001"] = "invalid-date"

    with pytest.raises(
        ValidationError,
        match="Invalid validated order date",
    ):
        run_validation(payments, reference_data)


def test_future_reference_order_date_raises_error(
    payments,
    reference_data,
):
    reference_data["valid_order_dates"]["ORD001"] = "2026-11-06"

    with pytest.raises(
        ValidationError,
        match="after the reference date",
    ):
        run_validation(payments, reference_data)


def test_invalid_expected_order_total_raises_error(
    payments,
    reference_data,
):
    reference_data["expected_order_totals"]["ORD001"] = "invalid"

    with pytest.raises(
        ValidationError,
        match="Invalid expected order total",
    ):
        run_validation(payments, reference_data)


def test_non_positive_expected_order_total_raises_error(
    payments,
    reference_data,
):
    reference_data["expected_order_totals"]["ORD001"] = "0"

    with pytest.raises(
        ValidationError,
        match="Invalid expected order total",
    ):
        run_validation(payments, reference_data)


# ---------------------------------------------------------------------
# Payment identifier validation
# ---------------------------------------------------------------------


def test_missing_payment_id_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "source_payment_id"] = None

    result = run_validation(dataframe, reference_data)

    assert result.rejected_count == 1

    assert "missing_payment_id" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_blank_payment_id_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "source_payment_id"] = "   "

    result = run_validation(dataframe, reference_data)

    assert result.rejected_count == 1


def test_duplicate_payment_ids_are_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[1, "source_payment_id"] = "PAY001"

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == 2
    assert result.rejected_count == 1

    codes = rejection_codes(
        result.rejected_records.iloc[0]
    )

    assert "duplicate_payment_id" in codes


def test_first_occurrence_remains_canonical_if_invalid(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = "-10"

    dataframe.loc[1, "source_payment_id"] = "PAY001"

    result = run_validation(dataframe, reference_data)

    first_rejected = result.rejected_records.iloc[0]

    assert "non_positive_payment_amount" in rejection_codes(
        first_rejected
    )

    second_rejected = result.rejected_records.iloc[1]

    assert "duplicate_payment_id" in rejection_codes(
        second_rejected
    )


# ---------------------------------------------------------------------
# Order reference validation
# ---------------------------------------------------------------------


def test_missing_order_reference_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "source_order_id"] = None

    result = run_validation(dataframe, reference_data)

    assert "missing_order_reference" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_unknown_order_reference_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "source_order_id"] = "UNKNOWN"

    result = run_validation(dataframe, reference_data)

    assert "invalid_order_reference" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_order_reference_is_trimmed(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "source_order_id"] = " ORD001 "

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == 3


# ---------------------------------------------------------------------
# Payment method validation
# ---------------------------------------------------------------------


def test_missing_payment_method_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_method"] = None

    result = run_validation(dataframe, reference_data)

    assert "missing_payment_method" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_unsupported_payment_method_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_method"] = "Cryptocurrency"

    result = run_validation(dataframe, reference_data)

    assert "unsupported_payment_method" in rejection_codes(
        result.rejected_records.iloc[0]
    )


# ---------------------------------------------------------------------
# Payment status validation
# ---------------------------------------------------------------------


def test_missing_payment_status_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_status"] = None

    result = run_validation(dataframe, reference_data)

    assert "missing_payment_status" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_unsupported_payment_status_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_status"] = "Unknown"

    result = run_validation(dataframe, reference_data)

    assert "unsupported_payment_status" in rejection_codes(
        result.rejected_records.iloc[0]
    )


# ---------------------------------------------------------------------
# Payment date validation
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_date",
    [
        None,
        "",
        "   ",
    ],
)
def test_missing_payment_date_is_rejected(
    payments,
    reference_data,
    invalid_date,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_date"] = invalid_date

    result = run_validation(dataframe, reference_data)

    assert "missing_payment_date" in rejection_codes(
        result.rejected_records.iloc[0]
    )


@pytest.mark.parametrize(
    "invalid_date",
    [
        "invalid-date",
        "2026-02-30",
        "05-10-2026",
        "20261002",
    ],
)
def test_invalid_payment_date_is_rejected(
    payments,
    reference_data,
    invalid_date,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_date"] = invalid_date

    result = run_validation(dataframe, reference_data)

    assert "invalid_payment_date" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_payment_before_order_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_date"] = "2026-09-30"

    result = run_validation(dataframe, reference_data)

    assert "payment_before_order" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_future_payment_date_is_rejected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_date"] = "2026-11-06"

    result = run_validation(dataframe, reference_data)

    assert "future_payment_date" in rejection_codes(
        result.rejected_records.iloc[0]
    )


# ---------------------------------------------------------------------
# Payment amount validation
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_amount",
    [
        None,
        "",
        "   ",
    ],
)
def test_missing_payment_amount_is_rejected(
    payments,
    reference_data,
    invalid_amount,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = invalid_amount

    result = run_validation(dataframe, reference_data)

    assert "missing_payment_amount" in rejection_codes(
        result.rejected_records.iloc[0]
    )


@pytest.mark.parametrize(
    "invalid_amount",
    [
        "not-a-number",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_payment_amount_is_rejected(
    payments,
    reference_data,
    invalid_amount,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = invalid_amount

    result = run_validation(dataframe, reference_data)

    assert "invalid_payment_amount" in rejection_codes(
        result.rejected_records.iloc[0]
    )


@pytest.mark.parametrize(
    "invalid_amount",
    [
        "0",
        "-1",
    ],
)
def test_non_positive_payment_amount_is_rejected(
    payments,
    reference_data,
    invalid_amount,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = invalid_amount

    result = run_validation(dataframe, reference_data)

    assert "non_positive_payment_amount" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_payment_amount_must_match_order_total(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = "99.99"

    result = run_validation(dataframe, reference_data)

    assert "payment_amount_mismatch" in rejection_codes(
        result.rejected_records.iloc[0]
    )


def test_payment_amount_matches_order_total_exactly(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_amount"] = "100.00"

    result = run_validation(dataframe, reference_data)

    assert result.valid_count == 3
    assert result.rejected_count == 0


# ---------------------------------------------------------------------
# Multiple validation issues
# ---------------------------------------------------------------------


def test_multiple_payment_issues_are_collected(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.loc[0, "payment_method"] = "Unknown"
    dataframe.loc[0, "payment_status"] = "Invalid"
    dataframe.loc[0, "payment_amount"] = "-10"

    result = run_validation(dataframe, reference_data)

    codes = rejection_codes(
        result.rejected_records.iloc[0]
    )

    assert "unsupported_payment_method" in codes
    assert "unsupported_payment_status" in codes
    assert "non_positive_payment_amount" in codes

    assert result.issue_count == 3


# ---------------------------------------------------------------------
# Input immutability
# ---------------------------------------------------------------------


def test_payment_validation_does_not_modify_input(
    payments,
    reference_data,
):
    original = payments.copy(deep=True)

    run_validation(payments, reference_data)

    pd.testing.assert_frame_equal(
        payments,
        original,
    )


def test_validation_preserves_original_dataframe_indexes(
    payments,
    reference_data,
):
    dataframe = payments.copy()

    dataframe.index = [10, 20, 30]

    dataframe.loc[20, "payment_amount"] = "-1"

    result = run_validation(dataframe, reference_data)

    assert result.rejected_records.index.tolist() == [20]
    assert result.valid_records.index.tolist() == [10, 30]
