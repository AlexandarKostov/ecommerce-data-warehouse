
"""
Tests for controlled data-quality issue injection.
"""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from config.data_generation import DATA_QUALITY_ISSUES
from src.data_generation.quality_injector import (
    QualityInjectionError,
    inject_data_quality_issues,
)


@pytest.fixture
def clean_datasets():
    """Create small, valid source datasets for testing."""

    return {
        "stg_customers": pd.DataFrame({
            "source_customer_id": [
                f"CUST{i:03d}" for i in range(1, 101)
            ],
            "first_name": ["John"] * 100,
            "last_name": ["Smith"] * 100,
            "email": [
                f"customer{i}@example.com"
                for i in range(1, 101)
            ],
            "phone": ["123456789"] * 100,
            "country": ["Germany"] * 100,
            "city": ["Berlin"] * 100,
            "registration_date": ["2026-01-01"] * 100,
        }),

        "stg_products": pd.DataFrame({
            "source_product_id": [
                f"PROD{i:03d}" for i in range(1, 101)
            ],
            "product_name": ["Product"] * 100,
            "category": ["Electronics"] * 100,
            "unit_price": ["100.00"] * 100,
            "unit_cost": ["60.00"] * 100,
            "stock_quantity": ["10"] * 100,
            "created_at_source": ["2026-01-01"] * 100,
        }),

        "stg_orders": pd.DataFrame({
            "source_order_id": [
                f"ORD{i:03d}" for i in range(1, 101)
            ],
            "source_customer_id": [
                f"CUST{i:03d}" for i in range(1, 101)
            ],
            "order_date": ["2026-01-01"] * 100,
            "order_status": ["Delivered"] * 100,
            "shipping_country": ["Germany"] * 100,
            "shipping_city": ["Berlin"] * 100,
        }),

        "stg_order_items": pd.DataFrame({
            "source_order_item_id": [
                f"ITEM{i:03d}" for i in range(1, 101)
            ],
            "source_order_id": [
                f"ORD{i:03d}" for i in range(1, 101)
            ],
            "source_product_id": [
                f"PROD{i:03d}" for i in range(1, 101)
            ],
            "quantity": ["2"] * 100,
            "unit_price": ["100.00"] * 100,
            "discount_amount": ["0.00"] * 100,
        }),

        "stg_payments": pd.DataFrame({
            "source_payment_id": [
                f"PAY{i:03d}" for i in range(1, 101)
            ],
            "source_order_id": [
                f"ORD{i:03d}" for i in range(1, 101)
            ],
            "payment_method": ["Credit Card"] * 100,
            "payment_status": ["Completed"] * 100,
            "payment_date": ["2026-01-01"] * 100,
            "payment_amount": ["200.00"] * 100,
        }),
    }


def test_injects_all_configured_quality_issues(clean_datasets):
    """All six configured issues must be injected."""

    result = inject_data_quality_issues(
        clean_datasets,
        seed=42,
    )

    assert (
        result["stg_customers"]["email"].eq("").sum()
        == 2
    )

    assert (
        result["stg_customers"]["source_customer_id"].duplicated().sum()
        == 1
    )

    assert (
        result["stg_products"]["unit_price"].eq("-10.00").sum()
        == 1
    )

    assert (
        result["stg_orders"]["order_date"].eq("").sum()
        == 0
    )

    assert (
        result["stg_orders"]["source_customer_id"]
        .str.startswith("INVALID_CUSTOMER_REF_").sum()
        == 0
    )

    assert len(result["stg_customers"]) == 101
    assert len(result["stg_payments"]) == 101

    assert (
        result["stg_payments"]["source_payment_id"].duplicated().sum()
        == 1
    )


def test_injection_is_reproducible(clean_datasets):
    """Identical inputs and seeds must produce identical outputs."""

    first_result = inject_data_quality_issues(
        clean_datasets,
        seed=42,
    )

    second_result = inject_data_quality_issues(
        clean_datasets,
        seed=42,
    )

    for table_name in clean_datasets:
        assert_frame_equal(
            first_result[table_name],
            second_result[table_name],
        )


def test_different_seeds_change_selected_records(clean_datasets):
    """Different seeds should normally select different records."""

    first_result = inject_data_quality_issues(
        clean_datasets,
        seed=42,
    )

    second_result = inject_data_quality_issues(
        clean_datasets,
        seed=99,
    )

    assert not first_result["stg_customers"].equals(
        second_result["stg_customers"]
    )


def test_original_datasets_remain_unchanged(clean_datasets):
    """Quality injection must never modify the original DataFrames."""

    original_datasets = {
        table_name: dataframe.copy(deep=True)
        for table_name, dataframe in clean_datasets.items()
    }

    inject_data_quality_issues(
        clean_datasets,
        seed=42,
    )

    for table_name in clean_datasets:
        assert_frame_equal(
            clean_datasets[table_name],
            original_datasets[table_name],
        )


def test_custom_issue_rates_are_supported(clean_datasets):
    """Custom issue rates must override configured defaults."""

    custom_rates = {
        issue_name: 0.10
        for issue_name in DATA_QUALITY_ISSUES
    }

    result = inject_data_quality_issues(
        clean_datasets,
        seed=42,
        issue_rates=custom_rates,
    )

    # Exactly 10 distinct customers must have missing emails.
    # Duplicate customer records may inherit the missing email.
    customers_with_missing_email = (
        result["stg_customers"]
        .loc[
            result["stg_customers"]["email"].eq(""),
            "source_customer_id",
        ]
        .nunique()
    )

    assert customers_with_missing_email == 10

    # 10 duplicate customer records must be appended.
    assert len(result["stg_customers"]) == 110

    # 10 products must have invalid prices.
    assert (
        result["stg_products"]["unit_price"]
        .eq("-10.00")
        .sum()
        == 10
    )

    # 10 orders must have missing dates.
    assert (
        result["stg_orders"]["order_date"]
        .eq("")
        .sum()
        == 10
    )

    # 10 orders must reference nonexistent customers.
    assert (
        result["stg_orders"]["source_customer_id"]
        .str.startswith("INVALID_CUSTOMER_REF_")
        .sum()
        == 10
    )

    # 10 duplicate payment records must be appended.
    assert len(result["stg_payments"]) == 110

    assert (
        result["stg_payments"]["source_payment_id"]
        .duplicated()
        .sum()
        == 10
    )

@pytest.mark.parametrize(
    "invalid_rate",
    [-0.01, 1.01, float("nan"), float("inf"), "invalid", True],
)
def test_invalid_issue_rates_are_rejected(
    clean_datasets,
    invalid_rate,
):
    """Invalid percentages must raise a descriptive exception."""

    custom_rates = {
        "missing_customer_email": invalid_rate,
    }

    with pytest.raises(QualityInjectionError):
        inject_data_quality_issues(
            clean_datasets,
            issue_rates=custom_rates,
        )


def test_unknown_issue_rate_is_rejected(clean_datasets):
    """Unsupported issue names must be rejected."""

    with pytest.raises(
        QualityInjectionError,
        match="Unsupported quality issues",
    ):
        inject_data_quality_issues(
            clean_datasets,
            issue_rates={
                "unknown_issue": 0.10,
            },
        )


def test_missing_dataset_is_rejected(clean_datasets):
    """All five required datasets must be provided."""

    del clean_datasets["stg_payments"]

    with pytest.raises(
        QualityInjectionError,
        match="Missing tables",
    ):
        inject_data_quality_issues(clean_datasets)


def test_missing_required_column_is_rejected(clean_datasets):
    """Required columns must exist before injection."""

    clean_datasets["stg_customers"] = (
        clean_datasets["stg_customers"]
        .drop(columns=["email"])
    )

    with pytest.raises(
        QualityInjectionError,
        match="missing required columns",
    ):
        inject_data_quality_issues(clean_datasets)


def test_invalid_seed_is_rejected(clean_datasets):
    """The random seed must be an integer."""

    with pytest.raises(
        QualityInjectionError,
        match="Seed must be an integer",
    ):
        inject_data_quality_issues(
            clean_datasets,
            seed="42",
        )
