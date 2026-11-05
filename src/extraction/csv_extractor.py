
"""
CSV extraction module.

Reads the five synthetic ecommerce source datasets from data/raw.

The extraction layer preserves raw source values. Data cleaning,
normalization, and business validation belong to transformation.
"""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


# Source CSV definitions and their corresponding staging tables.
SOURCE_DATASETS = {
    "stg_customers": {
        "file_name": "customers.csv",
        "columns": [
            "source_customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "country",
            "city",
            "registration_date",
        ],
    },
    "stg_products": {
        "file_name": "products.csv",
        "columns": [
            "source_product_id",
            "product_name",
            "category",
            "unit_price",
            "unit_cost",
            "stock_quantity",
            "created_at_source",
        ],
    },
    "stg_orders": {
        "file_name": "orders.csv",
        "columns": [
            "source_order_id",
            "source_customer_id",
            "order_date",
            "order_status",
            "shipping_country",
            "shipping_city",
        ],
    },
    "stg_order_items": {
        "file_name": "order_items.csv",
        "columns": [
            "source_order_item_id",
            "source_order_id",
            "source_product_id",
            "quantity",
            "unit_price",
            "discount_amount",
        ],
    },
    "stg_payments": {
        "file_name": "payments.csv",
        "columns": [
            "source_payment_id",
            "source_order_id",
            "payment_method",
            "payment_status",
            "payment_date",
            "payment_amount",
        ],
    },
}


class CSVExtractionError(Exception):
    """Raised when a source CSV cannot be extracted or validated."""


def extract_csv_files(
    data_directory: Path | str = DEFAULT_RAW_DATA_DIR,
) -> dict[str, pd.DataFrame]:
    """
    Extract all configured CSV datasets.

    Args:
        data_directory: Directory containing the source CSV files.

    Returns:
        Dictionary keyed by staging table name. Each DataFrame
        contains the original source columns plus source_file.

    Raises:
        CSVExtractionError: If a file is missing, empty, unreadable,
        or does not match its expected source schema.
    """

    data_directory = Path(data_directory)

    if not data_directory.is_dir():
        raise CSVExtractionError(
            f"Raw data directory does not exist: {data_directory}"
        )

    extracted_datasets = {}

    for staging_table, configuration in SOURCE_DATASETS.items():
        file_name = configuration["file_name"]
        expected_columns = configuration["columns"]
        file_path = data_directory / file_name

        if not file_path.is_file():
            raise CSVExtractionError(
                f"Source file not found: {file_path}"
            )

        try:
            dataframe = pd.read_csv(
                file_path,
                dtype=str,
                encoding="utf-8",
                keep_default_na=False,
                na_filter=False,
                on_bad_lines="error",
            )
        except (OSError, UnicodeError, pd.errors.ParserError) as error:
            raise CSVExtractionError(
                f"Unable to read source file '{file_name}': {error}"
            ) from error

        if dataframe.empty:
            raise CSVExtractionError(
                f"Source file contains no records: {file_name}"
            )

        actual_columns = list(dataframe.columns)

        missing_columns = [
            column
            for column in expected_columns
            if column not in actual_columns
        ]

        unexpected_columns = [
            column
            for column in actual_columns
            if column not in expected_columns
        ]

        if missing_columns or unexpected_columns:
            raise CSVExtractionError(
                f"Invalid schema in '{file_name}'. "
                f"Missing columns: {missing_columns}. "
                f"Unexpected columns: {unexpected_columns}."
            )

        # Keep the expected source column order.
        dataframe = dataframe[expected_columns].copy()

        # Preserve the source filename for staging lineage.
        dataframe["source_file"] = file_name

        extracted_datasets[staging_table] = dataframe

    return extracted_datasets
