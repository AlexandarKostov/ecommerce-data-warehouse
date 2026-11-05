"""
Generate intentionally imperfect ecommerce source datasets.

This module orchestrates the existing CSV extractor and quality
injector. Clean source files remain untouched in data/raw.

Output:
    data/quality/customers.csv
    data/quality/products.csv
    data/quality/orders.csv
    data/quality/order_items.csv
    data/quality/payments.csv
"""

from pathlib import Path
from collections.abc import Mapping

import pandas as pd

from config.data_generation import RANDOM_SEED
from src.data_generation.quality_injector import (
    inject_data_quality_issues,
)
from src.extraction.csv_extractor import (
    DEFAULT_RAW_DATA_DIR,
    SOURCE_DATASETS,
    extract_csv_files,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUALITY_DATA_DIR = PROJECT_ROOT / "data" / "quality"


class QualityDatasetGenerationError(Exception):
    """Raised when quality dataset generation or saving fails."""


def generate_quality_datasets(
    raw_data_directory: Path | str = DEFAULT_RAW_DATA_DIR,
    output_directory: Path | str = DEFAULT_QUALITY_DATA_DIR,
    seed: int = RANDOM_SEED,
    issue_rates: Mapping[str, float] | None = None,
) -> dict[str, Path]:
    """
    Generate and save imperfect copies of the clean source datasets.

    Args:
        raw_data_directory:
            Directory containing the five clean source CSV files.

        output_directory:
            Directory where imperfect CSV files will be saved.

        seed:
            Random seed for reproducible issue injection.

        issue_rates:
            Optional overrides for configured quality issue rates.

    Returns:
        Dictionary mapping staging table names to generated file paths.

    Raises:
        QualityDatasetGenerationError:
            If the output directory would overwrite the clean source
            directory or if saving the datasets fails.

        CSVExtractionError:
            If the clean source datasets cannot be extracted.

        QualityInjectionError:
            If the datasets, seed, or issue rates are invalid.
    """

    raw_data_directory = Path(raw_data_directory).resolve()
    output_directory = Path(output_directory).resolve()

    # Never allow imperfect datasets to overwrite clean source files.
    if raw_data_directory == output_directory:
        raise QualityDatasetGenerationError(
            "The quality output directory cannot be the raw data directory."
        )

    # Extract the clean source datasets.
    clean_datasets = extract_csv_files(
        data_directory=raw_data_directory,
    )

    # Inject controlled quality issues into independent DataFrame copies.
    quality_datasets = inject_data_quality_issues(
        datasets=clean_datasets,
        seed=seed,
        issue_rates=issue_rates,
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    generated_files = {}

    try:
        for staging_table, dataframe in quality_datasets.items():
            file_name = SOURCE_DATASETS[staging_table]["file_name"]
            output_file = output_directory / file_name

            # source_file is extraction metadata, not a source column.
            output_dataframe = dataframe.drop(
                columns=["source_file"],
                errors="ignore",
            )

            output_dataframe.to_csv(
                output_file,
                index=False,
                encoding="utf-8",
            )

            generated_files[staging_table] = output_file

    except OSError as error:
        raise QualityDatasetGenerationError(
            f"Unable to save quality datasets: {error}"
        ) from error

    return generated_files


if __name__ == "__main__":

    print("=" * 65)
    print("E-COMMERCE QUALITY DATASET GENERATION")
    print("=" * 65)

    generated_files = generate_quality_datasets()

    total_records = 0

    print("\nGenerated datasets:")

    for staging_table, file_path in generated_files.items():
        dataframe = pd.read_csv(
            file_path,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )

        record_count = len(dataframe)
        total_records += record_count

        print(
            f"{staging_table:<20} "
            f"{record_count:>10,} records"
        )

        print(f"  {file_path}")

    print("\n" + "=" * 65)
    print("QUALITY DATASET GENERATION COMPLETED")
    print("=" * 65)

    print(f"Total records: {total_records:,}")
    print(f"Output directory: {DEFAULT_QUALITY_DATA_DIR}")