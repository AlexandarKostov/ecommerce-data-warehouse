import pandas as pd
import pytest

from config.data_generation import REFERENCE_DATE
from src.transformation.validation.orders import (
    validate_orders,
)
from src.transformation.validation_result import ValidationError


VALID_CUSTOMER_IDS = {"C001", "C002", "C003"}


def make_orders(data=None):
    """Create a small valid order dataset for testing."""

    if data is None:
        data = {
            "staging_id": [1, 2],
            "source_order_id": ["O001", "O002"],
            "source_customer_id": ["C001", "C002"],
            "order_date": ["2026-10-01", "2026-10-02"],
            "order_status": ["Processing", "Delivered"],
        }

    return pd.DataFrame(data)


def get_issue_codes(result, row_position=0):
    """Return validation issue codes for a rejected row."""

    reasons = result.rejected_records.iloc[row_position][
        "rejection_reasons"
    ]

    return {reason["code"] for reason in reasons}


def test_valid_orders_pass_validation():
    result = validate_orders(
        make_orders(),
        VALID_CUSTOMER_IDS,
    )

    assert result.valid_count == 2
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_missing_order_id_is_rejected():
    dataframe = make_orders(
        {
            "source_order_id": ["", "O002"],
            "source_customer_id": ["C001", "C002"],
            "order_date": ["2026-10-01", "2026-10-02"],
            "order_status": ["Processing", "Delivered"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 1
    assert result.rejected_count == 1
    assert "MISSING_ORDER_ID" in get_issue_codes(result)


def test_duplicate_order_ids_are_rejected():
    dataframe = make_orders(
        {
            "staging_id": [1, 2, 3],
            "source_order_id": ["O001", "O002", "O001"],
            "source_customer_id": ["C001", "C002", "C003"],
            "order_date": [
                "2026-10-01",
                "2026-10-02",
                "2026-10-03",
            ],
            "order_status": [
                "Processing",
                "Delivered",
                "Pending",
            ],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 2
    assert result.rejected_count == 1

    assert result.valid_records["staging_id"].tolist() == [1, 2]
    assert result.rejected_records["staging_id"].tolist() == [3]

    assert "DUPLICATE_ORDER_ID" in get_issue_codes(result)


def test_duplicate_order_id_comparison_ignores_whitespace():
    dataframe = make_orders(
        {
            "source_order_id": ["O001", " O001 "],
            "source_customer_id": ["C001", "C002"],
            "order_date": ["2026-10-01", "2026-10-02"],
            "order_status": ["Processing", "Delivered"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 1
    assert result.rejected_count == 1
    assert "DUPLICATE_ORDER_ID" in get_issue_codes(result)


def test_missing_customer_reference_is_rejected():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": [""],
            "order_date": ["2026-10-01"],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert "MISSING_CUSTOMER_REFERENCE" in get_issue_codes(result)


def test_unknown_customer_reference_is_rejected():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C999"],
            "order_date": ["2026-10-01"],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert "INVALID_CUSTOMER_REFERENCE" in get_issue_codes(result)


def test_customer_reference_comparison_ignores_whitespace():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": [" C001 "],
            "order_date": ["2026-10-01"],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 1
    assert result.rejected_count == 0


def test_missing_order_date_is_rejected():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": [""],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert "MISSING_ORDER_DATE" in get_issue_codes(result)


@pytest.mark.parametrize(
    "order_date",
    [
        "not-a-date",
        "2026-13-01",
        "2026-02-30",
        "01-10-2026",
        "2026/10/01",
    ],
)
def test_invalid_order_dates_are_rejected(order_date):
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": [order_date],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert "INVALID_ORDER_DATE" in get_issue_codes(result)


def test_future_order_date_is_rejected():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": ["2099-01-01"],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert "FUTURE_ORDER_DATE" in get_issue_codes(result)


def test_configured_reference_date_is_valid():
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": [REFERENCE_DATE],
            "order_status": ["Processing"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 1
    assert result.rejected_count == 0


@pytest.mark.parametrize(
    "order_status",
    [
        "Unknown",
        "Completed",
        "In Progress",
        " ",
    ],
)
def test_invalid_order_statuses_are_rejected(order_status):
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": ["2026-10-01"],
            "order_status": [order_status],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1

    expected_code = (
        "MISSING_ORDER_STATUS"
        if not order_status.strip()
        else "INVALID_ORDER_STATUS"
    )

    assert expected_code in get_issue_codes(result)


@pytest.mark.parametrize(
    "order_status",
    [
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled",
        "Returned",
        " pending ",
    ],
)
def test_supported_order_statuses_are_accepted(order_status):
    dataframe = make_orders(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
            "order_date": ["2026-10-01"],
            "order_status": [order_status],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 1
    assert result.rejected_count == 0


def test_order_can_have_multiple_validation_issues():
    dataframe = make_orders(
        {
            "source_order_id": [""],
            "source_customer_id": ["C999"],
            "order_date": ["2099-01-01"],
            "order_status": ["Unknown"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.rejected_count == 1
    assert result.issue_count == 4

    assert get_issue_codes(result) == {
        "MISSING_ORDER_ID",
        "INVALID_CUSTOMER_REFERENCE",
        "FUTURE_ORDER_DATE",
        "INVALID_ORDER_STATUS",
    }


def test_first_occurrence_remains_canonical_if_it_has_other_errors():
    dataframe = make_orders(
        {
            "source_order_id": ["O001", "O001"],
            "source_customer_id": ["C999", "C001"],
            "order_date": ["2026-10-01", "2026-10-02"],
            "order_status": ["Processing", "Delivered"],
        }
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 0
    assert result.rejected_count == 2

    assert "INVALID_CUSTOMER_REFERENCE" in get_issue_codes(result, 0)
    assert "DUPLICATE_ORDER_ID" in get_issue_codes(result, 1)


def test_valid_customer_ids_must_be_a_set():
    with pytest.raises(ValidationError, match="set or frozenset"):
        validate_orders(make_orders(), ["C001", "C002"])


def test_missing_required_columns_raise_validation_error():
    dataframe = pd.DataFrame(
        {
            "source_order_id": ["O001"],
            "source_customer_id": ["C001"],
        }
    )

    with pytest.raises(ValidationError, match="order_date"):
        validate_orders(dataframe, VALID_CUSTOMER_IDS)


def test_original_order_dataframe_is_not_modified():
    dataframe = make_orders(
        {
            "source_order_id": ["O001", "O001"],
            "source_customer_id": ["C001", "C999"],
            "order_date": ["2026-10-01", "2099-01-01"],
            "order_status": ["Processing", "Unknown"],
        }
    )

    original = dataframe.copy(deep=True)

    validate_orders(dataframe, VALID_CUSTOMER_IDS)

    pd.testing.assert_frame_equal(dataframe, original)


def test_empty_order_dataset_returns_empty_result():
    dataframe = pd.DataFrame(
        columns=[
            "source_order_id",
            "source_customer_id",
            "order_date",
            "order_status",
        ]
    )

    result = validate_orders(dataframe, VALID_CUSTOMER_IDS)

    assert result.valid_count == 0
    assert result.rejected_count == 0
    assert result.issue_count == 0