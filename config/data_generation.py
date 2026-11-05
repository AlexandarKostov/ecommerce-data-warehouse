
"""
Configuration for synthetic ecommerce data generation.
"""

# Reproducibility:
# Using the same seed allows us to reproduce the same random dataset.
RANDOM_SEED = 42
REFERENCE_DATE = "2026-11-05"
# Target dataset sizes
CUSTOMER_COUNT = 10_000
PRODUCT_COUNT = 1_000
ORDER_COUNT = 25_000

# Output directory
RAW_DATA_DIR = "data/raw"

# Controlled data quality issues
# These percentages will be used later when generating intentionally
# imperfect source records for ETL validation.
DATA_QUALITY_ISSUES = {
    "missing_customer_email": 0.02,
    "duplicate_customers": 0.01,
    "invalid_product_price": 0.01,
    "missing_order_date": 0.005,
    "invalid_customer_reference": 0.005,
    "duplicate_payments": 0.01,
}

