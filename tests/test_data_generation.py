
import pandas as pd
import pytest
from decimal import Decimal

from config.data_generation import REFERENCE_DATE

from src.data_generation.generator import (
    generate_customers,
    generate_products,
    generate_orders,
    generate_order_items,
    generate_payments,
)


def generate_test_dataset(seed=42):
    """Generate a small, reproducible dataset for testing."""

    customers = generate_customers(count=10, seed=seed)
    products = generate_products(count=10, seed=seed)

    orders = generate_orders(
        customers=customers,
        count=10,
        seed=seed,
    )

    order_items = generate_order_items(
        orders=orders,
        products=products,
        seed=seed,
    )

    payments = generate_payments(
        orders=orders,
        order_items=order_items,
        seed=seed,
    )

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "payments": payments,
    }


@pytest.fixture
def dataset():
    """Shared test dataset."""
    return generate_test_dataset()


def test_source_ids_are_unique(dataset):
    """Every source entity must have unique identifiers."""

    assert dataset["customers"].source_customer_id.is_unique
    assert dataset["products"].source_product_id.is_unique
    assert dataset["orders"].source_order_id.is_unique
    assert dataset["order_items"].source_order_item_id.is_unique
    assert dataset["payments"].source_payment_id.is_unique


def test_referential_integrity(dataset):
    """Every foreign source ID must reference an existing record."""

    customers = dataset["customers"]
    products = dataset["products"]
    orders = dataset["orders"]
    items = dataset["order_items"]
    payments = dataset["payments"]

    assert orders.source_customer_id.isin(
        customers.source_customer_id
    ).all()

    assert items.source_order_id.isin(
        orders.source_order_id
    ).all()

    assert items.source_product_id.isin(
        products.source_product_id
    ).all()

    assert payments.source_order_id.isin(
        orders.source_order_id
    ).all()


def test_every_order_has_items(dataset):
    """Every generated order must contain at least one item."""

    order_ids = set(dataset["orders"].source_order_id)
    item_order_ids = set(dataset["order_items"].source_order_id)

    assert order_ids == item_order_ids


def test_every_order_has_payment_records(dataset):
    """Every generated order must have at least one payment record."""

    order_ids = set(dataset["orders"].source_order_id)
    payment_order_ids = set(dataset["payments"].source_order_id)

    assert order_ids == payment_order_ids


def test_required_fields_are_not_missing(dataset):
    """The clean baseline dataset must not contain missing values."""

    for name, dataframe in dataset.items():
        assert dataframe.notna().all().all(), (
            f"Missing values detected in {name}"
        )


def test_product_financial_rules(dataset):
    """Product costs must not exceed their selling prices."""

    products = dataset["products"]

    for product in products.itertuples():
        price = Decimal(str(product.unit_price))
        cost = Decimal(str(product.unit_cost))

        assert price > 0
        assert cost > 0
        assert cost <= price


def test_order_item_financial_rules(dataset):
    """Quantities, prices and discounts must be valid."""

    items = dataset["order_items"]

    for item in items.itertuples():
        quantity = Decimal(str(item.quantity))
        price = Decimal(str(item.unit_price))
        discount = Decimal(str(item.discount_amount))

        gross_revenue = quantity * price

        assert quantity > 0
        assert price > 0
        assert discount >= 0
        assert discount <= gross_revenue


def test_payment_rules(dataset):
    """Payment records must contain valid amounts and categories."""

    payments = dataset["payments"]

    allowed_statuses = {
        "Completed",
        "Failed",
        "Pending",
        "Refunded",
    }

    allowed_methods = {
        "Credit Card",
        "Debit Card",
        "PayPal",
        "Bank Transfer",
        "Cash on Delivery",
    }

    assert (payments.payment_amount.map(Decimal) > 0).all()

    assert set(payments.payment_status).issubset(
        allowed_statuses
    )

    assert set(payments.payment_method).issubset(
        allowed_methods
    )


def test_order_and_payment_dates(dataset):
    """Order and payment dates must follow chronological rules."""

    customers = dataset["customers"]
    orders = dataset["orders"]
    payments = dataset["payments"]

    reference_date = pd.Timestamp(REFERENCE_DATE)

    customer_registration = customers.set_index(
        "source_customer_id"
    )["registration_date"]

    order_dates = pd.to_datetime(orders.order_date, errors="coerce")
    registration_dates = pd.to_datetime(
        orders.source_customer_id.map(customer_registration),
        errors="coerce",
    )

    payment_dates = pd.to_datetime(
        payments.payment_date,
        errors="coerce",
    )

    payment_order_dates = pd.to_datetime(
        payments.source_order_id.map(
            orders.set_index("source_order_id")["order_date"]
        ),
        errors="coerce",
    )

    assert order_dates.notna().all()
    assert registration_dates.notna().all()
    assert payment_dates.notna().all()
    assert payment_order_dates.notna().all()

    assert (order_dates >= registration_dates).all()
    assert (payment_dates >= payment_order_dates).all()

    assert (order_dates <= reference_date).all()
    assert (payment_dates <= reference_date).all()


def test_payment_amounts_match_order_totals(dataset):
    """
    Every payment attempt must represent the full net order amount.

    Failed attempts are included because they represent attempted
    transactions, not captured revenue.
    """

    items = dataset["order_items"]
    payments = dataset["payments"]

    order_totals = {}

    for order_id, group in items.groupby("source_order_id"):

        total = Decimal("0.00")

        for item in group.itertuples():
            quantity = Decimal(str(item.quantity))
            price = Decimal(str(item.unit_price))
            discount = Decimal(str(item.discount_amount))

            total += (quantity * price) - discount

        order_totals[order_id] = total

    for payment in payments.itertuples():
        expected_amount = order_totals[payment.source_order_id]
        actual_amount = Decimal(str(payment.payment_amount))

        assert actual_amount == expected_amount


def test_generation_is_reproducible():
    """Identical seeds must produce identical datasets."""

    first = generate_test_dataset(seed=42)
    second = generate_test_dataset(seed=42)

    for dataset_name in first:
        pd.testing.assert_frame_equal(
            first[dataset_name],
            second[dataset_name],
        )



# ---------------------------------------------------------
# Negative tests: Payment input validation
# ---------------------------------------------------------


def test_payment_rejects_missing_order_item_id_column(dataset):
    """Order items must contain their source identifier."""

    items = dataset["order_items"].drop(
        columns=["source_order_item_id"]
    )

    with pytest.raises(
        ValueError,
        match="Order items DataFrame is missing columns",
    ):
        generate_payments(dataset["orders"], items)


def test_payment_rejects_missing_order_item_id(dataset):
    """Order item identifiers cannot be missing."""

    items = dataset["order_items"].copy()
    items.loc[items.index[0], "source_order_item_id"] = None

    with pytest.raises(
        ValueError,
        match="Order item IDs cannot contain missing values",
    ):
        generate_payments(dataset["orders"], items)


def test_payment_rejects_duplicate_order_item_ids(dataset):
    """Order item identifiers must be unique."""

    items = dataset["order_items"].copy()

    items.loc[
        items.index[1],
        "source_order_item_id",
    ] = items.iloc[0]["source_order_item_id"]

    with pytest.raises(
        ValueError,
        match="Order item IDs must be unique",
    ):
        generate_payments(dataset["orders"], items)


def test_payment_rejects_missing_order_item_reference(dataset):
    """Order items must reference an existing order."""

    items = dataset["order_items"].copy()
    items.loc[items.index[0], "source_order_id"] = None

    with pytest.raises(
        ValueError,
        match="Order item references cannot contain missing values",
    ):
        generate_payments(dataset["orders"], items)


def test_payment_rejects_unknown_order_reference(dataset):
    """Order items cannot reference nonexistent orders."""

    items = dataset["order_items"].copy()

    items.loc[
        items.index[0],
        "source_order_id",
    ] = "UNKNOWN_ORDER"

    with pytest.raises(
        ValueError,
        match="Every order must have order items",
    ):
        generate_payments(dataset["orders"], items)


def test_payment_rejects_orders_without_items(dataset):
    """Every order must have at least one order item."""

    orders = dataset["orders"].copy()
    items = dataset["order_items"].copy()

    order_id = orders.iloc[0]["source_order_id"]

    items = items[
        items["source_order_id"] != order_id
    ]

    with pytest.raises(
        ValueError,
        match="Every order must have order items",
    ):
        generate_payments(orders, items)


def test_payment_rejects_unsupported_order_status(dataset):
    """Only supported order statuses are accepted."""

    orders = dataset["orders"].copy()

    orders.loc[
        orders.index[0],
        "order_status",
    ] = "Unknown Status"

    with pytest.raises(
        ValueError,
        match="Unsupported order statuses",
    ):
        generate_payments(orders, dataset["order_items"])


def test_payment_rejects_missing_order_status(dataset):
    """Order statuses cannot be missing."""

    orders = dataset["orders"].copy()
    orders.loc[orders.index[0], "order_status"] = None

    with pytest.raises(
        ValueError,
        match="Order statuses cannot contain missing values",
    ):
        generate_payments(orders, dataset["order_items"])


def test_payment_rejects_invalid_order_date(dataset):
    """Order dates must be valid ISO dates."""

    orders = dataset["orders"].copy()

    orders.loc[
        orders.index[0],
        "order_date",
    ] = "invalid-date"

    with pytest.raises(
        ValueError,
        match="Invalid order date",
    ):
        generate_payments(orders, dataset["order_items"])


def test_payment_rejects_future_order_date(dataset):
    """Order dates cannot exceed the reference date."""

    orders = dataset["orders"].copy()

    orders.loc[
        orders.index[0],
        "order_date",
    ] = "2026-11-06"

    with pytest.raises(
        ValueError,
        match="has a date after the reference date",
    ):
        generate_payments(orders, dataset["order_items"])


@pytest.mark.parametrize(
    ("column", "invalid_value", "expected_error"),
    [
        (
            "quantity",
            "not-a-number",
            "Invalid numeric value",
        ),
        (
            "quantity",
            0,
            "Quantity must be a positive whole number",
        ),
        (
            "quantity",
            1.5,
            "Quantity must be a positive whole number",
        ),
        (
            "unit_price",
            "not-a-number",
            "Invalid numeric value",
        ),
        (
            "unit_price",
            0,
            "Invalid unit price",
        ),
        (
            "discount_amount",
            -1,
            "Invalid discount",
        ),
        (
            "discount_amount",
            999999,
            "Discount exceeds gross amount",
        ),
    ],
)
def test_payment_rejects_invalid_order_item_values(
    dataset,
    column,
    invalid_value,
    expected_error,
):
    """Invalid quantities, prices and discounts must be rejected."""

    items = dataset["order_items"].copy()

    # Object dtype allows us to test invalid string values safely.
    items[column] = items[column].astype(object)

    items.loc[
        items.index[0],
        column,
    ] = invalid_value

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        generate_payments(dataset["orders"], items)
