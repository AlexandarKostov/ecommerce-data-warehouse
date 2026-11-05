
"""
Controlled data-quality issue injection.

Creates intentionally imperfect copies of the clean synthetic
ecommerce datasets for testing ETL validation and transformation.

The original DataFrames are never modified.

Supported issues:
- Missing customer emails.
- Duplicate customer records.
- Invalid product prices.
- Missing order dates.
- Invalid customer references.
- Duplicate payment records.
"""

import random
from collections.abc import Mapping
from math import isfinite
from typing import Any

import pandas as pd

from config.data_generation import (
    DATA_QUALITY_ISSUES,
    RANDOM_SEED,
)


REQUIRED_DATASETS = {
    "stg_customers": {
        "source_customer_id",
        "email",
    },
    "stg_products": {
        "source_product_id",
        "unit_price",
    },
    "stg_orders": {
        "source_order_id",
        "source_customer_id",
        "order_date",
    },
    "stg_order_items": {
        "source_order_item_id",
        "source_order_id",
        "source_product_id",
    },
    "stg_payments": {
        "source_payment_id",
        "source_order_id",
    },
}


class QualityInjectionError(Exception):
    """Raised when data-quality issues cannot be injected safely."""


def _validate_datasets(
    datasets: Mapping[str, pd.DataFrame],
) -> None:
    """Validate the supplied datasets before injecting issues."""

    if not isinstance(datasets, Mapping):
        raise QualityInjectionError(
            "Datasets must be supplied as a dictionary or mapping."
        )

    expected_tables = set(REQUIRED_DATASETS)
    actual_tables = set(datasets)

    missing_tables = expected_tables - actual_tables
    unexpected_tables = actual_tables - expected_tables

    if missing_tables or unexpected_tables:
        raise QualityInjectionError(
            "Invalid dataset collection. "
            f"Missing tables: {sorted(missing_tables)}. "
            f"Unexpected tables: {sorted(unexpected_tables)}."
        )

    for table_name, required_columns in REQUIRED_DATASETS.items():
        dataframe = datasets[table_name]

        if not isinstance(dataframe, pd.DataFrame):
            raise QualityInjectionError(
                f"{table_name} must contain a pandas DataFrame."
            )

        missing_columns = (
            required_columns - set(dataframe.columns)
        )

        if missing_columns:
            raise QualityInjectionError(
                f"{table_name} is missing required columns: "
                f"{sorted(missing_columns)}."
            )


def _validate_issue_rates(
    issue_rates: Mapping[str, float],
) -> dict[str, float]:
    """Validate issue percentages and return normalized rates."""

    if not isinstance(issue_rates, Mapping):
        raise QualityInjectionError(
            "Issue rates must be supplied as a dictionary or mapping."
        )

    expected_issues = set(DATA_QUALITY_ISSUES)
    actual_issues = set(issue_rates)

    unexpected_issues = actual_issues - expected_issues

    if unexpected_issues:
        raise QualityInjectionError(
            f"Unsupported quality issues: "
            f"{sorted(unexpected_issues)}."
        )

    validated_rates = {}

    for issue_name in expected_issues:
        rate = issue_rates.get(
            issue_name,
            DATA_QUALITY_ISSUES[issue_name],
        )

        if isinstance(rate, bool):
            raise QualityInjectionError(
                f"Invalid rate for '{issue_name}': {rate}."
            )

        try:
            rate = float(rate)
        except (TypeError, ValueError) as error:
            raise QualityInjectionError(
                f"Invalid rate for '{issue_name}': {rate}."
            ) from error

        if not isfinite(rate) or not 0 <= rate <= 1:
            raise QualityInjectionError(
                f"Rate for '{issue_name}' must be between 0 and 1."
            )

        validated_rates[issue_name] = rate

    return validated_rates


def _calculate_issue_count(
    record_count: int,
    rate: float,
) -> int:
    """Calculate the number of original records affected."""

    return int(record_count * rate)


def _select_positions(
    record_count: int,
    issue_count: int,
    rng: random.Random,
) -> list[int]:
    """Select unique row positions reproducibly."""

    if issue_count == 0:
        return []

    return rng.sample(
        range(record_count),
        issue_count,
    )


def inject_data_quality_issues(
    datasets: Mapping[str, pd.DataFrame],
    seed: int = RANDOM_SEED,
    issue_rates: Mapping[str, float] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Inject configured data-quality issues into clean datasets.

    Args:
        datasets:
            Dictionary containing all five clean DataFrames,
            keyed by staging table name.

        seed:
            Random seed used for reproducible record selection.

        issue_rates:
            Optional dictionary overriding individual configured
            issue percentages. Unspecified issues use defaults.

    Returns:
        A new dictionary containing imperfect copies of all
        five original datasets.

    Notes:
        - Original DataFrames are never modified.
        - Issue counts are calculated from original row counts.
        - Duplicate records are appended to their datasets.
        - All other issues modify selected records.
        - Invalid values remain strings for downstream ETL validation.

    Raises:
        QualityInjectionError:
            If datasets, columns, rates, or seed are invalid.
    """

    _validate_datasets(datasets)

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise QualityInjectionError(
            "Seed must be an integer."
        )

    if issue_rates is None:
        issue_rates = DATA_QUALITY_ISSUES

    rates = _validate_issue_rates(issue_rates)

    # Use a local random generator to avoid changing global random state.
    rng = random.Random(seed)

    # Deep copies protect the original clean datasets.
    clean_datasets = {
        table_name: dataframe.copy(deep=True).reset_index(drop=True)
        for table_name, dataframe in datasets.items()
    }

    quality_datasets = {
        table_name: dataframe.copy(deep=True)
        for table_name, dataframe in clean_datasets.items()
    }

    # Calculate issue counts using original dataset sizes.
    issue_counts = {
        issue_name: _calculate_issue_count(
            len(clean_datasets[table_name]),
            rates[issue_name],
        )
        for issue_name, table_name in {
            "missing_customer_email": "stg_customers",
            "duplicate_customers": "stg_customers",
            "invalid_product_price": "stg_products",
            "missing_order_date": "stg_orders",
            "invalid_customer_reference": "stg_orders",
            "duplicate_payments": "stg_payments",
        }.items()
    }

    # ---------------------------------------------------------
    # 1. Missing customer emails
    # ---------------------------------------------------------

    customers = quality_datasets["stg_customers"]

    selected_positions = _select_positions(
        len(customers),
        issue_counts["missing_customer_email"],
        rng,
    )

    if selected_positions:
        customers.loc[
            selected_positions,
            "email",
        ] = ""

    # ---------------------------------------------------------
    # 2. Duplicate customer records
    # ---------------------------------------------------------

    duplicate_count = issue_counts["duplicate_customers"]

    selected_positions = _select_positions(
        len(customers),
        duplicate_count,
        rng,
    )

    if selected_positions:
        duplicate_customers = customers.iloc[
            selected_positions
        ].copy()

        quality_datasets["stg_customers"] = pd.concat(
            [
                customers,
                duplicate_customers,
            ],
            ignore_index=True,
        )

    # ---------------------------------------------------------
    # 3. Invalid product prices
    # ---------------------------------------------------------

    products = quality_datasets["stg_products"]

    selected_positions = _select_positions(
        len(products),
        issue_counts["invalid_product_price"],
        rng,
    )

    if selected_positions:
        products.loc[
            selected_positions,
            "unit_price",
        ] = "-10.00"

    # ---------------------------------------------------------
    # 4. Missing order dates
    # ---------------------------------------------------------

    orders = quality_datasets["stg_orders"]

    selected_positions = _select_positions(
        len(orders),
        issue_counts["missing_order_date"],
        rng,
    )

    if selected_positions:
        orders.loc[
            selected_positions,
            "order_date",
        ] = ""

    # ---------------------------------------------------------
    # 5. Invalid customer references
    # ---------------------------------------------------------

    selected_positions = _select_positions(
        len(orders),
        issue_counts["invalid_customer_reference"],
        rng,
    )

    if selected_positions:
        invalid_references = [
            f"INVALID_CUSTOMER_REF_{seed}_{position}"
            for position in selected_positions
        ]

        orders.loc[
            selected_positions,
            "source_customer_id",
        ] = invalid_references

    # ---------------------------------------------------------
    # 6. Duplicate payment records
    # ---------------------------------------------------------

    payments = quality_datasets["stg_payments"]

    selected_positions = _select_positions(
        len(payments),
        issue_counts["duplicate_payments"],
        rng,
    )

    if selected_positions:
        duplicate_payments = payments.iloc[
            selected_positions
        ].copy()

        quality_datasets["stg_payments"] = pd.concat(
            [
                payments,
                duplicate_payments,
            ],
            ignore_index=True,
        )

    return quality_datasets
