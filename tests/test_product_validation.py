import pandas as pd
import pytest

from src.transformation.validation.products import (
    validate_products,
)
from src.transformation.validation_result import ValidationError


def make_products(data=None):
    """Create a small valid product dataset for testing."""

    if data is None:
        data = {
            "staging_id": [1, 2],
            "source_product_id": ["P001", "P002"],
            "product_name": ["Laptop", "Keyboard"],
            "unit_price": ["1200.00", "75.50"],
            "unit_cost": ["850.00", "40.00"],
            "stock_quantity": ["10", "25"],
        }

    return pd.DataFrame(data)


def get_issue_codes(result, row_position=0):
    """Return validation issue codes for a rejected row."""

    reasons = result.rejected_records.iloc[row_position][
        "rejection_reasons"
    ]

    return {reason["code"] for reason in reasons}


def test_valid_products_pass_validation():
    result = validate_products(make_products())

    assert result.valid_count == 2
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_missing_product_id_is_rejected():
    dataframe = make_products(
        {
            "source_product_id": ["", "P002"],
            "product_name": ["Laptop", "Keyboard"],
            "unit_price": ["1200.00", "75.50"],
            "unit_cost": ["850.00", "40.00"],
            "stock_quantity": ["10", "25"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 1
    assert "MISSING_PRODUCT_ID" in get_issue_codes(result)


def test_missing_product_name_is_rejected():
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["  "],
            "unit_price": ["1200.00"],
            "unit_cost": ["850.00"],
            "stock_quantity": ["10"],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1
    assert "MISSING_PRODUCT_NAME" in get_issue_codes(result)


def test_missing_unit_price_is_rejected():
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": [""],
            "unit_cost": ["850.00"],
            "stock_quantity": ["10"],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1
    assert "MISSING_UNIT_PRICE" in get_issue_codes(result)


@pytest.mark.parametrize(
    "unit_price",
    [
        "invalid",
        "-10.00",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_unit_prices_are_rejected(unit_price):
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": [unit_price],
            "unit_cost": ["850.00"],
            "stock_quantity": ["10"],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1
    assert "INVALID_UNIT_PRICE" in get_issue_codes(result)


def test_zero_unit_price_is_valid():
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Promotional Product"],
            "unit_price": ["0.00"],
            "unit_cost": ["0.00"],
            "stock_quantity": ["0"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 0


def test_missing_unit_cost_is_allowed():
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": ["1200.00"],
            "unit_cost": [""],
            "stock_quantity": ["10"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 0


@pytest.mark.parametrize(
    "unit_cost",
    [
        "invalid",
        "-1.00",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_unit_costs_are_rejected(unit_cost):
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": ["1200.00"],
            "unit_cost": [unit_cost],
            "stock_quantity": ["10"],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1
    assert "INVALID_UNIT_COST" in get_issue_codes(result)


@pytest.mark.parametrize(
    "stock_quantity",
    [
        "",
        "-1",
        "1.5",
        "invalid",
        "NaN",
        "Infinity",
    ],
)
def test_invalid_stock_quantities_are_rejected(stock_quantity):
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": ["1200.00"],
            "unit_cost": ["850.00"],
            "stock_quantity": [stock_quantity],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1

    expected_code = (
        "MISSING_STOCK_QUANTITY"
        if stock_quantity == ""
        else "INVALID_STOCK_QUANTITY"
    )

    assert expected_code in get_issue_codes(result)


def test_whole_number_decimal_stock_quantity_is_valid():
    dataframe = make_products(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
            "unit_price": ["1200.00"],
            "unit_cost": ["850.00"],
            "stock_quantity": ["10.0"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 0


def test_duplicate_product_ids_are_rejected():
    dataframe = make_products(
        {
            "staging_id": [1, 2, 3],
            "source_product_id": ["P001", "P002", "P001"],
            "product_name": ["Laptop", "Keyboard", "Duplicate Laptop"],
            "unit_price": ["1200.00", "75.50", "1100.00"],
            "unit_cost": ["850.00", "40.00", "800.00"],
            "stock_quantity": ["10", "25", "5"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 2
    assert result.rejected_count == 1

    assert result.valid_records["staging_id"].tolist() == [1, 2]
    assert result.rejected_records["staging_id"].tolist() == [3]

    assert "DUPLICATE_PRODUCT_ID" in get_issue_codes(result)


def test_duplicate_comparison_ignores_surrounding_whitespace():
    dataframe = make_products(
        {
            "source_product_id": ["P001", " P001 "],
            "product_name": ["Laptop", "Second Laptop"],
            "unit_price": ["1200.00", "1100.00"],
            "unit_cost": ["850.00", "800.00"],
            "stock_quantity": ["10", "5"],
        }
    )

    result = validate_products(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 1
    assert "DUPLICATE_PRODUCT_ID" in get_issue_codes(result)


def test_product_can_have_multiple_validation_issues():
    dataframe = make_products(
        {
            "source_product_id": [""],
            "product_name": [""],
            "unit_price": ["-10.00"],
            "unit_cost": ["invalid"],
            "stock_quantity": ["1.5"],
        }
    )

    result = validate_products(dataframe)

    assert result.rejected_count == 1
    assert result.issue_count == 5

    assert get_issue_codes(result) == {
        "MISSING_PRODUCT_ID",
        "MISSING_PRODUCT_NAME",
        "INVALID_UNIT_PRICE",
        "INVALID_UNIT_COST",
        "INVALID_STOCK_QUANTITY",
    }


def test_missing_required_columns_raise_validation_error():
    dataframe = pd.DataFrame(
        {
            "source_product_id": ["P001"],
            "product_name": ["Laptop"],
        }
    )

    with pytest.raises(ValidationError, match="unit_price"):
        validate_products(dataframe)


def test_original_product_dataframe_is_not_modified():
    dataframe = make_products(
        {
            "source_product_id": ["P001", "P001"],
            "product_name": ["Laptop", "Duplicate Laptop"],
            "unit_price": ["1200.00", "1100.00"],
            "unit_cost": ["850.00", "800.00"],
            "stock_quantity": ["10", "5"],
        }
    )

    original = dataframe.copy(deep=True)

    validate_products(dataframe)

    pd.testing.assert_frame_equal(dataframe, original)


def test_empty_product_dataset_returns_empty_result():
    dataframe = pd.DataFrame(
        columns=[
            "source_product_id",
            "product_name",
            "unit_price",
            "unit_cost",
            "stock_quantity",
        ]
    )

    result = validate_products(dataframe)

    assert result.valid_count == 0
    assert result.rejected_count == 0
    assert result.issue_count == 0