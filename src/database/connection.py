
"""
Database connection management.

Creates and manages the SQLAlchemy connection to the MySQL
data warehouse using credentials stored in the project .env file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def get_database_engine() -> Engine:
    """
    Create a SQLAlchemy engine using environment configuration.

    Credentials are loaded from the project root .env file.
    """

    load_dotenv(dotenv_path=ENV_FILE)

    required_variables = [
        "DB_HOST",
        "DB_PORT",
        "DB_DATABASE",
        "DB_USERNAME",
        "DB_PASSWORD",
    ]

    missing_variables = [
        variable
        for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing_variables:
        raise EnvironmentError(
            "Missing required database environment variables: "
            + ", ".join(missing_variables)
        )

    database_url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_DATABASE"),
    )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        hide_parameters=True,
    )


def test_database_connection(engine: Engine) -> bool:
    """
    Test the database connection with a simple query.

    Returns True when the connection succeeds.
    Raises the original SQLAlchemy exception on failure.
    """

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True
