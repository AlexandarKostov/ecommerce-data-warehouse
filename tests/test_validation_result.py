
import pandas as pd
import pytest

from src.transformation.validation_result import (
    ValidationError,
    ValidationIssue,
    create_validation_result,
)


def test_separates_valid_and_rejected_records():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2, 3],
            "source_product_id": ["P001", "P002", "P003"],
            "unit_price": ["10.00", "-5.00", "25.00"],
        }
    )

    issues = {
        1: [
            ValidationIssue(
                code="NEGATIVE_UNIT_PRICE",
                field="unit_price",
                message="Unit price cannot be negative.",
            )
        ]
    }

    result = create_validation_result(dataframe, issues)

    assert result.valid_count == 2
    assert result.rejected_count == 1
    assert result.total_count == 3
    assert result.issue_count == 1

    assert result.valid_records["staging_id"].tolist() == [1, 3]
    assert result.rejected_records["staging_id"].tolist() == [2]


def test_collects_multiple_issues_for_one_record():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1],
            "product_name": [""],
            "unit_price": ["invalid"],
        }
    )

    issues = {
        0: [
            ValidationIssue(
                code="MISSING_PRODUCT_NAME",
                field="product_name",
                message="Product name is required.",
            ),
            ValidationIssue(
                code="INVALID_UNIT_PRICE",
                field="unit_price",
                message="Unit price must be numeric.",
            ),
        ]
    }

    result = create_validation_result(dataframe, issues)

    assert result.rejected_count == 1
    assert result.issue_count == 2

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert len(reasons) == 2
    assert reasons[0]["code"] == "MISSING_PRODUCT_NAME"
    assert reasons[1]["code"] == "INVALID_UNIT_PRICE"


def test_preserves_original_dataframe():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2],
            "source_customer_id": ["C001", "C002"],
            "email": ["valid@example.com", ""],
        }
    )

    original = dataframe.copy(deep=True)

    issues = {
        1: [
            ValidationIssue(
                code="MISSING_EMAIL",
                field="email",
                message="Customer email is required.",
            )
        ]
    }

    create_validation_result(dataframe, issues)

    pd.testing.assert_frame_equal(dataframe, original)


def test_supports_duplicate_dataframe_index_labels():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2, 3],
            "value": ["A", "B", "C"],
        },
        index=[0, 0, 1],
    )

    issues = {
        1: [
            ValidationIssue(
                code="INVALID_VALUE",
                field="value",
                message="Invalid value.",
            )
        ]
    }

    result = create_validation_result(dataframe, issues)

    assert result.valid_records["staging_id"].tolist() == [1, 3]
    assert result.rejected_records["staging_id"].tolist() == [2]


def test_rejects_invalid_row_position():
    dataframe = pd.DataFrame({"value": ["A"]})

    issues = {
        5: [
            ValidationIssue(
                code="INVALID_VALUE",
                field="value",
                message="Invalid value.",
            )
        ]
    }

    with pytest.raises(ValidationError):
        create_validation_result(dataframe, issues)


def test_rejects_empty_issue_list():
    dataframe = pd.DataFrame({"value": ["A"]})

    with pytest.raises(ValidationError):
        create_validation_result(dataframe, {0: []})


def test_empty_input_returns_empty_result():
    dataframe = pd.DataFrame(columns=["staging_id", "value"])

    result = create_validation_result(dataframe, {})

    assert result.valid_count == 0
    assert result.rejected_count == 0
    assert result.issue_count == 0
    assert result.total_count == 0


def test_all_records_can_be_rejected():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2],
            "value": ["A", "B"],
        }
    )

    issues = {
        0: [
            ValidationIssue(
                code="INVALID_VALUE",
                field="value",
                message="Invalid value.",
            )
        ],
        1: [
            ValidationIssue(
                code="INVALID_VALUE",
                field="value",
                message="Invalid value.",
            )
        ],
    }

    result = create_validation_result(dataframe, issues)

    assert result.valid_count == 0
    assert result.rejected_count == 2
    assert result.issue_count == 2
