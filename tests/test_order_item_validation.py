import pandas as pd
import pytest
from decimal import Decimal

from src.transformation.validation.order_items import (
    validate_order_items,
)
from src.transformation.validation_result import ValidationError


@pytest.fixture
def order_items():
    return pd.DataFrame(
        [
            {
                "source_order_item_id": "ITEM001",
                "source_order_id": "ORD001",
                "source_product_id": "PROD001",
                "quantity": "2",
                "unit_price": "100.00",
                "discount_amount": "10.00",
            },
            {
                "source_order_item_id": "ITEM002",
                "source_order_id": "ORD002",
                "source_product_id": "PROD002",
                "quantity": "3",
                "unit_price": "50.00",
                "discount_amount": "15.00",
            },
        ]
    )


@pytest.fixture
def valid_order_ids():
    return {"ORD001", "ORD002"}


@pytest.fixture
def valid_product_ids():
    return {"PROD001", "PROD002"}


def test_valid_order_items_pass_validation(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_missing_order_item_id_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_order_item_id"] = ""

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1
    assert result.rejected_records.iloc[0]["source_order_item_id"] == ""


def test_duplicate_order_item_ids_are_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[1, "source_order_item_id"] = "ITEM001"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 1
    assert result.rejected_count == 1

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert any(
    issue["code"] == "duplicate_order_item_id"
    for issue in reasons
    )


def test_duplicate_item_id_comparison_ignores_whitespace(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[1, "source_order_item_id"] = " ITEM001 "

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_first_occurrence_remains_canonical_if_invalid(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "unit_price"] = "-10"
    order_items.loc[1, "source_order_item_id"] = "ITEM001"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 2

    first_rejected = result.rejected_records.iloc[0]
    second_rejected = result.rejected_records.iloc[1]

    first_codes = {
    issue["code"]
    for issue in first_rejected["rejection_reasons"]
    }

    second_codes = {
    issue["code"]
    for issue in second_rejected["rejection_reasons"]
    }

    assert "invalid_unit_price" in first_codes
    assert "duplicate_order_item_id" in second_codes


def test_missing_order_reference_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_order_id"] = ""

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_unknown_order_reference_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_order_id"] = "UNKNOWN_ORDER"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_order_reference_comparison_ignores_whitespace(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_order_id"] = " ORD001 "

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2


def test_missing_product_reference_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_product_id"] = ""

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_unknown_product_reference_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_product_id"] = "UNKNOWN_PRODUCT"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_product_reference_comparison_ignores_whitespace(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_product_id"] = " PROD001 "

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2


@pytest.mark.parametrize(
    "quantity",
    [
        "",
        " ",
        "0",
        "-1",
        "1.5",
        "invalid",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_quantities_are_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
    quantity,
):
    order_items.loc[0, "quantity"] = quantity

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


@pytest.mark.parametrize(
    "quantity",
    [
        "1",
        "10",
        "10.0",
        "10.000",
    ],
)
def test_positive_whole_number_quantities_are_accepted(
    order_items,
    valid_order_ids,
    valid_product_ids,
    quantity,
):
    order_items.loc[0, "quantity"] = quantity

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2


@pytest.mark.parametrize(
    "unit_price",
    [
        "",
        "0",
        "-10.00",
        "invalid",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_unit_prices_are_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
    unit_price,
):
    order_items.loc[0, "unit_price"] = unit_price

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


@pytest.mark.parametrize(
    "discount",
    [
        "",
        "-0.01",
        "invalid",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_discounts_are_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
    discount,
):
    order_items.loc[0, "discount_amount"] = discount

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1


def test_zero_discount_is_valid(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "discount_amount"] = "0.00"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2


def test_discount_equal_to_gross_revenue_is_valid(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "discount_amount"] = "200.00"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2


def test_discount_exceeding_gross_revenue_is_rejected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "discount_amount"] = "200.01"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert any(
    issue["code"] == "discount_exceeds_gross_revenue"
    for issue in reasons
    )


def test_multiple_validation_issues_are_collected(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "source_order_id"] = "UNKNOWN_ORDER"
    order_items.loc[0, "source_product_id"] = "UNKNOWN_PRODUCT"
    order_items.loc[0, "quantity"] = "0"
    order_items.loc[0, "unit_price"] = "-10"
    order_items.loc[0, "discount_amount"] = "-5"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.rejected_count == 1
    assert result.issue_count == 5


def test_valid_references_must_be_sets(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    with pytest.raises(ValidationError):
        validate_order_items(
            order_items,
            list(valid_order_ids),
            valid_product_ids,
        )

    with pytest.raises(ValidationError):
        validate_order_items(
            order_items,
            valid_order_ids,
            list(valid_product_ids),
        )


def test_missing_required_columns_raise_validation_error(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items = order_items.drop(columns=["discount_amount"])

    with pytest.raises(
        ValidationError,
        match="missing required columns",
    ):
        validate_order_items(
            order_items,
            valid_order_ids,
            valid_product_ids,
        )


def test_original_dataframe_is_not_modified(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    original = order_items.copy(deep=True)

    validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    pd.testing.assert_frame_equal(order_items, original)


def test_empty_order_items_return_empty_result(
    valid_order_ids,
    valid_product_ids,
):
    dataframe = pd.DataFrame(
        columns=[
            "source_order_item_id",
            "source_order_id",
            "source_product_id",
            "quantity",
            "unit_price",
            "discount_amount",
        ]
    )

    result = validate_order_items(
        dataframe,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 0
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_empty_valid_reference_sets_reject_all_records(order_items):
    result = validate_order_items(
        order_items,
        set(),
        set(),
    )

    assert result.rejected_count == 2
    assert result.valid_count == 0


def test_decimal_financial_calculation_avoids_float_precision_errors(
    order_items,
    valid_order_ids,
    valid_product_ids,
):
    order_items.loc[0, "quantity"] = "3"
    order_items.loc[0, "unit_price"] = "0.10"
    order_items.loc[0, "discount_amount"] = "0.30"

    result = validate_order_items(
        order_items,
        valid_order_ids,
        valid_product_ids,
    )

    assert result.valid_count == 2