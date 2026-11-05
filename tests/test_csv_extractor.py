
"""
Tests for the CSV extraction module.

All tests use temporary directories and synthetic CSV files.
They do not modify production source datasets.
"""

import pandas as pd
import pytest

from src.extraction.csv_extractor import (
    CSVExtractionError,
    SOURCE_DATASETS,
    extract_csv_files,
)


@pytest.fixture
def source_directory(tmp_path):
    """
    Create all five valid source CSV files in a temporary directory.
    """

    for configuration in SOURCE_DATASETS.values():
        file_path = tmp_path / configuration["file_name"]
        columns = configuration["columns"]

        record = {
            column: f"value_{column}"
            for column in columns
        }

        pd.DataFrame(
            [record],
            columns=columns,
        ).to_csv(
            file_path,
            index=False,
            encoding="utf-8",
        )

    return tmp_path


def test_extracts_all_five_datasets(source_directory):
    """All five source CSV files must be extracted successfully."""

    datasets = extract_csv_files(source_directory)

    assert set(datasets) == set(SOURCE_DATASETS)

    for staging_table, configuration in SOURCE_DATASETS.items():

        dataframe = datasets[staging_table]

        expected_columns = (
            configuration["columns"] + ["source_file"]
        )

        assert list(dataframe.columns) == expected_columns
        assert len(dataframe) == 1

        assert (
            dataframe["source_file"].iloc[0]
            == configuration["file_name"]
        )


def test_missing_source_file_raises_error(source_directory):
    """A missing source CSV must raise a descriptive exception."""

    missing_file = (
        source_directory
        / SOURCE_DATASETS["stg_payments"]["file_name"]
    )

    missing_file.unlink()

    with pytest.raises(
        CSVExtractionError,
        match="Source file not found",
    ):
        extract_csv_files(source_directory)


def test_missing_source_column_raises_error(source_directory):
    """A CSV missing an expected column must be rejected."""

    configuration = SOURCE_DATASETS["stg_customers"]

    file_path = source_directory / configuration["file_name"]

    invalid_columns = [
        column
        for column in configuration["columns"]
        if column != "email"
    ]

    pd.DataFrame(
        [{"source_customer_id": "CUST000001"}],
        columns=invalid_columns,
    ).to_csv(
        file_path,
        index=False,
        encoding="utf-8",
    )

    with pytest.raises(
        CSVExtractionError,
        match="Missing columns",
    ):
        extract_csv_files(source_directory)


def test_unexpected_source_column_raises_error(source_directory):
    """Unexpected CSV columns must be rejected."""

    configuration = SOURCE_DATASETS["stg_products"]

    file_path = source_directory / configuration["file_name"]

    columns = configuration["columns"] + ["unexpected_column"]

    record = {
        column: f"value_{column}"
        for column in columns
    }

    pd.DataFrame([record]).to_csv(
        file_path,
        index=False,
        encoding="utf-8",
    )

    with pytest.raises(
        CSVExtractionError,
        match="Unexpected columns",
    ):
        extract_csv_files(source_directory)


def test_preserves_empty_strings_and_literal_na(source_directory):
    """
    Empty strings and literal NA values must not be converted to NaN.
    """

    configuration = SOURCE_DATASETS["stg_customers"]

    file_path = source_directory / configuration["file_name"]

    record = {
        column: f"value_{column}"
        for column in configuration["columns"]
    }

    record["email"] = ""
    record["phone"] = "NA"

    pd.DataFrame(
        [record],
        columns=configuration["columns"],
    ).to_csv(
        file_path,
        index=False,
        encoding="utf-8",
    )

    datasets = extract_csv_files(source_directory)

    customers = datasets["stg_customers"]

    assert customers["email"].iloc[0] == ""
    assert customers["phone"].iloc[0] == "NA"

    assert pd.notna(customers["email"].iloc[0])
    assert pd.notna(customers["phone"].iloc[0])


def test_preserves_identifiers_as_strings(source_directory):
    """
    Identifiers with leading zeros must remain unchanged.
    """

    configuration = SOURCE_DATASETS["stg_customers"]

    file_path = source_directory / configuration["file_name"]

    record = {
        column: f"value_{column}"
        for column in configuration["columns"]
    }

    record["source_customer_id"] = "00001234"

    pd.DataFrame(
        [record],
        columns=configuration["columns"],
    ).to_csv(
        file_path,
        index=False,
        encoding="utf-8",
    )

    datasets = extract_csv_files(source_directory)

    customers = datasets["stg_customers"]

    actual_id = customers["source_customer_id"].iloc[0]

    assert actual_id == "00001234"
    assert isinstance(actual_id, str)


def test_missing_data_directory_raises_error(tmp_path):
    """A nonexistent raw data directory must be rejected."""

    missing_directory = tmp_path / "nonexistent"

    with pytest.raises(
        CSVExtractionError,
        match="Raw data directory does not exist",
    ):
        extract_csv_files(missing_directory)


def test_empty_source_file_raises_error(source_directory):
    """A CSV containing headers but no records must be rejected."""

    configuration = SOURCE_DATASETS["stg_orders"]

    file_path = source_directory / configuration["file_name"]

    pd.DataFrame(
        columns=configuration["columns"]
    ).to_csv(
        file_path,
        index=False,
        encoding="utf-8",
    )

    with pytest.raises(
        CSVExtractionError,
        match="contains no records",
    ):
        extract_csv_files(source_directory)
