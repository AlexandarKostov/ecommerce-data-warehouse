
"""
Shared validation result structures.

All dataset validators use these classes to return valid and
rejected records in a consistent format.

Validation is performed in memory. This module does not interact
with the database or modify the original input DataFrame.
"""

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    """
    Represents one validation failure for a source record.
    """

    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """
        Convert the issue into a JSON-serializable dictionary.
        """

        return asdict(self)


@dataclass
class ValidationResult:
    """
    Contains the valid and rejected records from one dataset.

    rejected_records includes an additional rejection_reasons
    column containing a list of validation issue dictionaries.
    """

    valid_records: pd.DataFrame
    rejected_records: pd.DataFrame

    @property
    def valid_count(self) -> int:
        return len(self.valid_records)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_records)

    @property
    def total_count(self) -> int:
        return self.valid_count + self.rejected_count

    @property
    def issue_count(self) -> int:
        """
        Total number of individual validation failures.

        This can be greater than rejected_count because one
        record may have multiple validation failures.
        """

        if self.rejected_records.empty:
            return 0

        return sum(
            len(reasons)
            for reasons in self.rejected_records["rejection_reasons"]
        )


class ValidationError(Exception):
    """Raised when validation cannot be performed correctly."""


def create_validation_result(
    dataframe: pd.DataFrame,
    issues_by_position: dict[int, list[ValidationIssue]],
) -> ValidationResult:
    """
    Build a consistent validation result from positional row errors.

    Args:
        dataframe:
            Original input dataset. It is never modified.

        issues_by_position:
            Mapping of zero-based row positions to all validation
            issues identified for that row.

    Returns:
        ValidationResult containing separate valid and rejected
        DataFrames.

    Notes:
        - Row positions are used instead of DataFrame index labels.
        - This supports DataFrames with duplicate index labels.
        - Every rejected row retains its original columns and values.
        - Valid rows do not receive a rejection_reasons column.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise ValidationError(
            "Validation input must be a pandas DataFrame."
        )

    if not isinstance(issues_by_position, dict):
        raise ValidationError(
            "Validation issues must be provided as a dictionary."
        )

    row_count = len(dataframe)

    for position, issues in issues_by_position.items():

        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or position < 0
            or position >= row_count
        ):
            raise ValidationError(
                f"Invalid row position: {position!r}."
            )

        if not isinstance(issues, list) or not issues:
            raise ValidationError(
                f"Row position {position} must have at least "
                "one validation issue."
            )

        if not all(
            isinstance(issue, ValidationIssue)
            for issue in issues
        ):
            raise ValidationError(
                f"Invalid validation issue at row position {position}."
            )

    rejected_positions = set(issues_by_position)

    valid_positions = [
        position
        for position in range(row_count)
        if position not in rejected_positions
    ]

    rejected_records = dataframe.iloc[
        sorted(rejected_positions)
    ].copy()

    valid_records = dataframe.iloc[valid_positions].copy()

    if rejected_positions:
        rejected_records["rejection_reasons"] = [
            [
                issue.to_dict()
                for issue in issues_by_position[position]
            ]
            for position in sorted(rejected_positions)
        ]

    return ValidationResult(
        valid_records=valid_records,
        rejected_records=rejected_records,
    )
