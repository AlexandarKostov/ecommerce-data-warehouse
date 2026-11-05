
import pandas as pd
import pytest

from src.transformation.validation.customers import (
    validate_customers,
)
from src.transformation.validation_result import ValidationError


def test_valid_customers_pass_validation():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2],
            "source_customer_id": ["C001", "C002"],
            "email": [
                "alice@example.com",
                "bob@example.org",
            ],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 2
    assert result.rejected_count == 0
    assert result.issue_count == 0


def test_missing_customer_id_is_rejected():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["", "C002"],
            "email": [
                "alice@example.com",
                "bob@example.com",
            ],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 1

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert reasons[0]["code"] == "MISSING_CUSTOMER_ID"


def test_missing_email_is_rejected():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001", "C002"],
            "email": ["", "bob@example.com"],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 1

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert reasons[0]["code"] == "MISSING_EMAIL"


@pytest.mark.parametrize(
    "email",
    [
        "invalid-email",
        "missing-domain@",
        "@missing-user.com",
        "missing-domain@example",
        "contains spaces@example.com",
    ],
)
def test_invalid_email_formats_are_rejected(email):
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001"],
            "email": [email],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 0
    assert result.rejected_count == 1

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert reasons[0]["code"] == "INVALID_EMAIL"


def test_duplicate_customer_ids_are_rejected():
    dataframe = pd.DataFrame(
        {
            "staging_id": [1, 2, 3],
            "source_customer_id": ["C001", "C002", "C001"],
            "email": [
                "alice@example.com",
                "bob@example.com",
                "alice.duplicate@example.com",
            ],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 2
    assert result.rejected_count == 1

    assert result.valid_records["staging_id"].tolist() == [1, 2]
    assert result.rejected_records["staging_id"].tolist() == [3]

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert reasons[0]["code"] == "DUPLICATE_CUSTOMER_ID"


def test_duplicate_id_comparison_ignores_surrounding_whitespace():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001", " C001 "],
            "email": [
                "alice@example.com",
                "alice2@example.com",
            ],
        }
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 1
    assert result.rejected_count == 1


def test_customer_can_have_multiple_validation_issues():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["", "C002"],
            "email": ["", "bob@example.com"],
        }
    )

    result = validate_customers(dataframe)

    assert result.rejected_count == 1
    assert result.issue_count == 2

    reasons = result.rejected_records.iloc[0]["rejection_reasons"]

    assert {
        reason["code"] for reason in reasons
    } == {
        "MISSING_CUSTOMER_ID",
        "MISSING_EMAIL",
    }


def test_first_occurrence_is_retained_even_if_email_is_invalid():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001", "C001"],
            "email": [
                "invalid-email",
                "valid@example.com",
            ],
        }
    )

    result = validate_customers(dataframe)

    # The first occurrence is retained as the canonical occurrence,
    # but it is rejected because its email is invalid.
    # The second occurrence is rejected as a duplicate.
    assert result.valid_count == 0
    assert result.rejected_count == 2

    first_reasons = (
        result.rejected_records.iloc[0]["rejection_reasons"]
    )
    second_reasons = (
        result.rejected_records.iloc[1]["rejection_reasons"]
    )

    assert first_reasons[0]["code"] == "INVALID_EMAIL"
    assert second_reasons[0]["code"] == "DUPLICATE_CUSTOMER_ID"


def test_missing_required_columns_raise_validation_error():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001"],
        }
    )

    with pytest.raises(ValidationError, match="email"):
        validate_customers(dataframe)


def test_original_customer_dataframe_is_not_modified():
    dataframe = pd.DataFrame(
        {
            "source_customer_id": ["C001", "C001"],
            "email": [
                "alice@example.com",
                "alice2@example.com",
            ],
        }
    )

    original = dataframe.copy(deep=True)

    validate_customers(dataframe)

    pd.testing.assert_frame_equal(dataframe, original)


def test_empty_customer_dataset_returns_empty_result():
    dataframe = pd.DataFrame(
        columns=[
            "source_customer_id",
            "email",
        ]
    )

    result = validate_customers(dataframe)

    assert result.valid_count == 0
    assert result.rejected_count == 0
    assert result.issue_count == 0
