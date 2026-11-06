"""Tests for rejected-record persistence."""

import json

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.loading.rejected_records_loader import (
    RejectedRecordsLoadError,
    persist_rejected_records,
)


@pytest.fixture
def engine():
    """Create an isolated SQLite database for each test."""

    database = create_engine("sqlite+pysqlite:///:memory:")

    with database.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE etl_rejected_records (
                    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    etl_run_id INTEGER NOT NULL,
                    source_table TEXT NOT NULL,
                    staging_record_id INTEGER NOT NULL,
                    source_record_id TEXT,
                    rejection_reasons JSON NOT NULL,
                    raw_record JSON NOT NULL,
                    UNIQUE (etl_run_id, source_table, staging_record_id)
                )
                """
            )
        )

    yield database
    database.dispose()


def make_rejected_record(
    staging_id=101,
    source_record_id="CUST-001",
    rejection_reasons=None,
):
    """Build a representative rejected customer record."""

    if rejection_reasons is None:
        rejection_reasons = [
            {
                "code": "missing_email",
                "field": "email",
                "message": "Email is required.",
            }
        ]

    return {
        "staging_id": staging_id,
        "etl_run_id": 7,
        "source_customer_id": source_record_id,
        "first_name": "Alex",
        "last_name": "Smith",
        "email": "",
        "country": "North Macedonia",
        "source_file": "customers.csv",
        "rejection_reasons": rejection_reasons,
    }


def test_persists_rejected_records_with_correct_mapping(engine):
    dataframe = pd.DataFrame(
        [
            make_rejected_record(staging_id=101),
            make_rejected_record(
                staging_id=102,
                source_record_id="CUST-002",
            ),
        ]
    )

    with engine.begin() as connection:
        persisted_count = persist_rejected_records(
            connection,
            run_id=7,
            rejected_datasets={"stg_customers": dataframe},
        )

    assert persisted_count == 2

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    etl_run_id,
                    source_table,
                    staging_record_id,
                    source_record_id,
                    rejection_reasons,
                    raw_record
                FROM etl_rejected_records
                ORDER BY staging_record_id
                """
            )
        ).mappings().all()

    assert len(rows) == 2

    assert rows[0]["etl_run_id"] == 7
    assert rows[0]["source_table"] == "stg_customers"
    assert rows[0]["staging_record_id"] == 101
    assert rows[0]["source_record_id"] == "CUST-001"

    reasons = json.loads(rows[0]["rejection_reasons"])
    raw_record = json.loads(rows[0]["raw_record"])

    assert reasons[0]["code"] == "missing_email"
    assert raw_record["email"] == ""
    assert raw_record["source_file"] == "customers.csv"

    # Database metadata and rejection reasons are stored separately.
    assert "staging_id" not in raw_record
    assert "etl_run_id" not in raw_record
    assert "rejection_reasons" not in raw_record


def test_persists_multiple_reasons_for_one_physical_record(engine):
    reasons = [
        {
            "code": "missing_email",
            "field": "email",
            "message": "Email is required.",
        },
        {
            "code": "invalid_customer_id",
            "field": "source_customer_id",
            "message": "Customer identifier is invalid.",
        },
    ]

    dataframe = pd.DataFrame(
        [make_rejected_record(rejection_reasons=reasons)]
    )

    with engine.begin() as connection:
        persisted_count = persist_rejected_records(
            connection,
            run_id=7,
            rejected_datasets={"stg_customers": dataframe},
        )

    assert persisted_count == 1

    with engine.connect() as connection:
        stored_reasons = connection.execute(
            text(
                """
                SELECT rejection_reasons
                FROM etl_rejected_records
                """
            )
        ).scalar_one()

    assert json.loads(stored_reasons) == reasons


def test_returns_zero_when_all_rejected_datasets_are_empty(engine):
    with engine.begin() as connection:
        persisted_count = persist_rejected_records(
            connection,
            run_id=7,
            rejected_datasets={},
        )

    assert persisted_count == 0

    with engine.connect() as connection:
        row_count = connection.execute(
            text("SELECT COUNT(*) FROM etl_rejected_records")
        ).scalar_one()

    assert row_count == 0


def test_accepts_empty_dataframe_with_required_columns(engine):
    dataframe = pd.DataFrame(
        columns=[
            "staging_id",
            "source_customer_id",
            "rejection_reasons",
        ]
    )

    with engine.begin() as connection:
        persisted_count = persist_rejected_records(
            connection,
            run_id=7,
            rejected_datasets={"stg_customers": dataframe},
        )

    assert persisted_count == 0


def test_rejects_unsupported_source_table(engine):
    with engine.begin() as connection:
        with pytest.raises(
            RejectedRecordsLoadError,
            match="Unsupported source tables",
        ):
            persist_rejected_records(
                connection,
                run_id=7,
                rejected_datasets={
                    "customers": pd.DataFrame()
                },
            )


def test_rejects_dataframe_missing_required_columns(engine):
    dataframe = pd.DataFrame(
        [{"staging_id": 101}]
    )

    with engine.begin() as connection:
        with pytest.raises(
            RejectedRecordsLoadError,
            match="missing required columns",
        ):
            persist_rejected_records(
                connection,
                run_id=7,
                rejected_datasets={"stg_customers": dataframe},
            )


def test_rejects_duplicate_staging_ids(engine):
    dataframe = pd.DataFrame(
        [
            make_rejected_record(staging_id=101),
            make_rejected_record(staging_id=101),
        ]
    )

    with engine.begin() as connection:
        with pytest.raises(
            RejectedRecordsLoadError,
            match="duplicate staging_id",
        ):
            persist_rejected_records(
                connection,
                run_id=7,
                rejected_datasets={"stg_customers": dataframe},
            )


def test_rejects_records_without_rejection_reasons(engine):
    record = make_rejected_record(rejection_reasons=[])
    dataframe = pd.DataFrame([record])

    with engine.begin() as connection:
        with pytest.raises(
            RejectedRecordsLoadError,
            match="non-empty rejection_reasons",
        ):
            persist_rejected_records(
                connection,
                run_id=7,
                rejected_datasets={"stg_customers": dataframe},
            )


def test_does_not_commit_or_rollback_callers_transaction(engine):
    dataframe = pd.DataFrame(
        [make_rejected_record()]
    )

    connection = engine.connect()
    transaction = connection.begin()

    try:
        persisted_count = persist_rejected_records(
            connection,
            run_id=7,
            rejected_datasets={"stg_customers": dataframe},
        )

        assert persisted_count == 1
        assert transaction.is_active

        transaction.rollback()

    finally:
        connection.close()

    with engine.connect() as verification_connection:
        row_count = verification_connection.execute(
            text("SELECT COUNT(*) FROM etl_rejected_records")
        ).scalar_one()

    assert row_count == 0
