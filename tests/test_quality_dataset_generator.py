"""
Tests for quality dataset generation and persistence.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.data_generation.quality_dataset_generator import (
    QualityDatasetGenerationError,
    generate_quality_datasets,
)
from src.extraction.csv_extractor import SOURCE_DATASETS


@pytest.fixture
def source_directory(tmp_path):
    """Create five small, clean source CSV datasets."""

    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()

    for staging_table, configuration in SOURCE_DATASETS.items():
        columns = configuration["columns"]

        records = []

        for position in range(1, 101):
            record = {
                column: f"value_{position}"
                for column in columns
            }

            if staging_table == "stg_customers":
                record.update({
                    "source_customer_id": f"CUST{position}",
                    "email": f"customer{position}@example.com",
                })

            elif staging_table == "stg_products":
                record.update({
                    "source_product_id": f"PROD{position}",
                    "unit_price": "100.00",
                })

            elif staging_table == "stg_orders":
                record.update({
                    "source_order_id": f"ORD{position}",
                    "source_customer_id": f"CUST{position}",
                    "order_date": "2026-01-01",
                })

            elif staging_table == "stg_order_items":
                record.update({
                    "source_order_item_id": f"ITEM{position}",
                    "source_order_id": f"ORD{position}",
                    "source_product_id": f"PROD{position}",
                })

            elif staging_table == "stg_payments":
                record.update({
                    "source_payment_id": f"PAY{position}",
                    "source_order_id": f"ORD{position}",
                })

            records.append(record)

        dataframe = pd.DataFrame(
            records,
            columns=columns,
        )

        dataframe.to_csv(
            raw_directory / configuration["file_name"],
            index=False,
            encoding="utf-8",
        )

    return raw_directory


def test_generates_all_five_quality_datasets(
    source_directory,
    tmp_path,
):
    """All five imperfect CSV datasets must be generated."""

    output_directory = tmp_path / "quality"

    generated_files = generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=output_directory,
        seed=42,
    )

    assert len(generated_files) == 5

    for staging_table, configuration in SOURCE_DATASETS.items():
        output_file = generated_files[staging_table]

        assert output_file.is_file()
        assert output_file.parent == output_directory
        assert output_file.name == configuration["file_name"]


def test_generated_files_preserve_expected_source_schemas(
    source_directory,
    tmp_path,
):
    """Saved quality files must not contain extraction metadata."""

    output_directory = tmp_path / "quality"

    generated_files = generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=output_directory,
    )

    for staging_table, configuration in SOURCE_DATASETS.items():
        dataframe = pd.read_csv(
            generated_files[staging_table],
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )

        assert list(dataframe.columns) == configuration["columns"]
        assert "source_file" not in dataframe.columns


def test_custom_rates_are_applied_to_saved_datasets(
    source_directory,
    tmp_path,
):
    """Custom issue rates must be reflected in persisted CSV files."""

    output_directory = tmp_path / "quality"

    custom_rates = {
        "missing_customer_email": 0.10,
        "duplicate_customers": 0.10,
        "invalid_product_price": 0.10,
        "missing_order_date": 0.10,
        "invalid_customer_reference": 0.10,
        "duplicate_payments": 0.10,
    }

    generated_files = generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=output_directory,
        seed=42,
        issue_rates=custom_rates,
    )

    customers = pd.read_csv(
        generated_files["stg_customers"],
        dtype=str,
        keep_default_na=False,
    )

    products = pd.read_csv(
        generated_files["stg_products"],
        dtype=str,
        keep_default_na=False,
    )

    orders = pd.read_csv(
        generated_files["stg_orders"],
        dtype=str,
        keep_default_na=False,
    )

    payments = pd.read_csv(
        generated_files["stg_payments"],
        dtype=str,
        keep_default_na=False,
    )

    assert len(customers) == 110

    assert (
        customers.loc[
            customers["email"].eq(""),
            "source_customer_id",
        ].nunique()
        == 10
    )

    assert products["unit_price"].eq("-10.00").sum() == 10

    assert orders["order_date"].eq("").sum() == 10

    assert (
        orders["source_customer_id"]
        .str.startswith("INVALID_CUSTOMER_REF_")
        .sum()
        == 10
    )

    assert len(payments) == 110
    assert payments["source_payment_id"].duplicated().sum() == 10


def test_clean_source_files_remain_unchanged(
    source_directory,
    tmp_path,
):
    """Quality generation must never modify clean source files."""

    original_files = {
        file_path.name: file_path.read_bytes()
        for file_path in source_directory.glob("*.csv")
    }

    generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=tmp_path / "quality",
        seed=42,
    )

    for file_name, original_content in original_files.items():
        assert (
            source_directory / file_name
        ).read_bytes() == original_content


def test_raw_and_quality_directories_cannot_be_the_same(
    source_directory,
):
    """The generator must protect the original source directory."""

    with pytest.raises(QualityDatasetGenerationError):
        generate_quality_datasets(
            raw_data_directory=source_directory,
            output_directory=source_directory,
        )


def test_quality_generation_is_reproducible(
    source_directory,
    tmp_path,
):
    """The same seed must produce identical quality CSV files."""

    first_output = tmp_path / "quality_first"
    second_output = tmp_path / "quality_second"

    first_files = generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=first_output,
        seed=42,
    )

    second_files = generate_quality_datasets(
        raw_data_directory=source_directory,
        output_directory=second_output,
        seed=42,
    )

    for staging_table in SOURCE_DATASETS:
        first_dataframe = pd.read_csv(
            first_files[staging_table],
            dtype=str,
            keep_default_na=False,
        )

        second_dataframe = pd.read_csv(
            second_files[staging_table],
            dtype=str,
            keep_default_na=False,
        )

        pd.testing.assert_frame_equal(
            first_dataframe,
            second_dataframe,
        )