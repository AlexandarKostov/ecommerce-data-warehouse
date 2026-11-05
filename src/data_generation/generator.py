
"""
Generate synthetic ecommerce source data.

Datasets:
- Customers
- Products
- Orders
- Order items

All generated datasets are deterministic when the same seed,
configuration, and Faker version are used.
"""

import random
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from faker import Faker

from config.data_generation import (
    CUSTOMER_COUNT,
    ORDER_COUNT,
    PRODUCT_COUNT,
    RANDOM_SEED,
    RAW_DATA_DIR,
    REFERENCE_DATE,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Product categories, product names and realistic price ranges.
# Prices are expressed in cents to avoid floating-point calculations.
PRODUCT_CATALOG = {
    "Electronics": {
        "products": [
            "Wireless Headphones",
            "Bluetooth Speaker",
            "Smart Watch",
            "Mechanical Keyboard",
            "Wireless Mouse",
            "USB-C Hub",
            "Portable Charger",
            "Webcam",
            "Gaming Monitor",
            "External SSD",
        ],
        "price_range": (1500, 150000),
    },
    "Clothing": {
        "products": [
            "Cotton T-Shirt",
            "Denim Jeans",
            "Winter Jacket",
            "Hooded Sweatshirt",
            "Running Shorts",
            "Formal Shirt",
            "Summer Dress",
            "Sports Leggings",
            "Wool Sweater",
            "Casual Sneakers",
        ],
        "price_range": (1000, 25000),
    },
    "Home & Kitchen": {
        "products": [
            "Coffee Maker",
            "Blender",
            "Air Fryer",
            "Kitchen Knife Set",
            "Non-Stick Frying Pan",
            "Vacuum Cleaner",
            "Desk Lamp",
            "Bed Sheet Set",
            "Storage Organizer",
            "Electric Kettle",
        ],
        "price_range": (800, 80000),
    },
    "Books": {
        "products": [
            "Business Strategy Book",
            "Python Programming Guide",
            "Data Engineering Handbook",
            "Personal Finance Guide",
            "Mystery Novel",
            "Science Fiction Novel",
            "History Book",
            "Leadership Handbook",
            "Marketing Essentials",
            "Psychology Book",
        ],
        "price_range": (500, 8000),
    },
    "Sports & Outdoors": {
        "products": [
            "Yoga Mat",
            "Adjustable Dumbbells",
            "Running Shoes",
            "Fitness Resistance Bands",
            "Camping Tent",
            "Hiking Backpack",
            "Water Bottle",
            "Cycling Helmet",
            "Jump Rope",
            "Fitness Tracker",
        ],
        "price_range": (500, 60000),
    },
    "Beauty & Personal Care": {
        "products": [
            "Facial Cleanser",
            "Moisturizing Cream",
            "Hair Dryer",
            "Electric Toothbrush",
            "Shampoo",
            "Skin Care Set",
            "Perfume",
            "Hair Styling Brush",
            "Body Lotion",
            "Sunscreen",
        ],
        "price_range": (300, 30000),
    },
    "Toys & Games": {
        "products": [
            "Building Blocks Set",
            "Board Game",
            "Remote Control Car",
            "Educational Puzzle",
            "Action Figure",
            "Card Game",
            "Kids Drawing Set",
            "Strategy Game",
            "Toy Train Set",
            "Science Experiment Kit",
        ],
        "price_range": (500, 20000),
    },
    "Grocery": {
        "products": [
            "Organic Coffee Beans",
            "Green Tea",
            "Olive Oil",
            "Dark Chocolate",
            "Almond Butter",
            "Protein Bars",
            "Breakfast Cereal",
            "Mixed Nuts",
            "Honey",
            "Pasta",
        ],
        "price_range": (200, 10000),
    },
}

PAYMENT_METHODS = [
    "Credit Card",
    "Debit Card",
    "PayPal",
    "Bank Transfer",
    "Cash on Delivery",
]

# ---------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------

def get_date_range() -> tuple[date, date]:
    """Return a fixed five-year date range."""

    reference_date = date.fromisoformat(REFERENCE_DATE)

    start_date = date(
        year=reference_date.year - 5,
        month=reference_date.month,
        day=reference_date.day,
    )

    return start_date, reference_date


# ---------------------------------------------------------------------
# Customer generation
# ---------------------------------------------------------------------

def generate_customers(
    count: int = CUSTOMER_COUNT,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Generate synthetic ecommerce customer records."""

    if count <= 0:
        raise ValueError("Customer count must be greater than zero.")

    fake = Faker()
    fake.seed_instance(seed)

    start_date, reference_date = get_date_range()

    customers = []

    for customer_number in range(1, count + 1):
        customer = {
            "source_customer_id": f"CUST{customer_number:06d}",
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "country": fake.country(),
            "city": fake.city(),
            "registration_date": fake.date_between(
                start_date=start_date,
                end_date=reference_date,
            ).isoformat(),
        }

        customers.append(customer)

    return pd.DataFrame(customers)


# ---------------------------------------------------------------------
# Product generation
# ---------------------------------------------------------------------

def generate_products(
    count: int = PRODUCT_COUNT,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic ecommerce product records.

    Product prices and costs are generated in cents to avoid
    floating-point precision problems.
    """

    if count <= 0:
        raise ValueError("Product count must be greater than zero.")

    rng = random.Random(seed)

    fake = Faker()
    fake.seed_instance(seed)

    start_date, reference_date = get_date_range()

    categories = list(PRODUCT_CATALOG.keys())

    products = []

    for product_number in range(1, count + 1):

        category = rng.choice(categories)
        category_data = PRODUCT_CATALOG[category]

        product_name = rng.choice(category_data["products"])

        minimum_price, maximum_price = category_data["price_range"]

        # Generate the selling price in cents.
        price_cents = rng.randint(
            minimum_price,
            maximum_price,
        )

        # Generate a cost between 40% and 85% of the selling price.
        minimum_cost = (price_cents * 40) // 100
        maximum_cost = (price_cents * 85) // 100

        cost_cents = rng.randint(
            minimum_cost,
            maximum_cost,
        )

        # Convert integer cents into formatted decimal strings.
        unit_price = f"{price_cents // 100}.{price_cents % 100:02d}"
        unit_cost = f"{cost_cents // 100}.{cost_cents % 100:02d}"

        product = {
            "source_product_id": f"PROD{product_number:06d}",
            "product_name": product_name,
            "category": category,
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "stock_quantity": rng.randint(0, 1000),
            "created_at_source": fake.date_between(
                start_date=start_date,
                end_date=reference_date,
            ).isoformat(),
        }

        products.append(product)

    return pd.DataFrame(products)


# ---------------------------------------------------------------------
# Order generation
# ---------------------------------------------------------------------

def generate_orders(
    customers: pd.DataFrame,
    count: int = ORDER_COUNT,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic ecommerce orders.

    Every order references an existing customer.
    Order dates cannot precede customer registration dates.
    """

    if count <= 0:
        raise ValueError("Order count must be greater than zero.")

    required_columns = {
        "source_customer_id",
        "country",
        "city",
        "registration_date",
    }

    missing_columns = required_columns - set(customers.columns)

    if missing_columns:
        raise ValueError(
            f"Customers DataFrame is missing columns: {missing_columns}"
        )

    if customers.empty:
        raise ValueError("Customers DataFrame cannot be empty.")

    if customers["source_customer_id"].isna().any():
        raise ValueError("Customer IDs cannot contain missing values.")

    if customers["source_customer_id"].duplicated().any():
        raise ValueError("Customer IDs must be unique.")

    rng = random.Random(seed)

    reference_date = date.fromisoformat(REFERENCE_DATE)

    statuses = [
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled",
        "Returned",
    ]

    # Weighted distribution makes completed orders more common.
    status_weights = [8, 12, 12, 48, 12, 8]

    customer_records = customers.to_dict("records")

    orders = []

    for order_number in range(1, count + 1):

        customer = rng.choice(customer_records)

        registration_date = date.fromisoformat(
            str(customer["registration_date"])
        )

        if registration_date > reference_date:
            raise ValueError(
                "Customer registration date cannot be after "
                "the reference date."
            )

        days_available = (
            reference_date - registration_date
        ).days

        order_date = registration_date + timedelta(
            days=rng.randint(0, days_available)
        )

        order = {
            "source_order_id": f"ORD{order_number:08d}",
            "source_customer_id": customer["source_customer_id"],
            "order_date": order_date.isoformat(),
            "order_status": rng.choices(
                statuses,
                weights=status_weights,
                k=1,
            )[0],
            "shipping_country": customer["country"],
            "shipping_city": customer["city"],
        }

        orders.append(order)

    return pd.DataFrame(orders)


# ---------------------------------------------------------------------
# Order-item generation
# ---------------------------------------------------------------------

def generate_order_items(
    orders: pd.DataFrame,
    products: pd.DataFrame,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic ecommerce order items.

    Each order receives between 1 and 5 items.
    Every item references an existing order and product.

    discount_amount represents the total discount
    for the entire order-item line.
    """

    required_order_columns = {
        "source_order_id",
    }

    required_product_columns = {
        "source_product_id",
        "unit_price",
    }

    missing_order_columns = (
        required_order_columns - set(orders.columns)
    )

    missing_product_columns = (
        required_product_columns - set(products.columns)
    )

    if missing_order_columns:
        raise ValueError(
            f"Orders DataFrame is missing columns: {missing_order_columns}"
        )

    if missing_product_columns:
        raise ValueError(
            f"Products DataFrame is missing columns: {missing_product_columns}"
        )

    if orders.empty or products.empty:
        raise ValueError("Orders and products cannot be empty.")

    if orders["source_order_id"].isna().any():
        raise ValueError("Order IDs cannot contain missing values.")

    if orders["source_order_id"].duplicated().any():
        raise ValueError("Order IDs must be unique.")

    if products["source_product_id"].isna().any():
        raise ValueError("Product IDs cannot contain missing values.")

    if products["source_product_id"].duplicated().any():
        raise ValueError("Product IDs must be unique.")

    rng = random.Random(seed)

    order_records = orders.to_dict("records")
    product_records = products.to_dict("records")

    order_items = []

    item_number = 1

    for order in order_records:

        # Every order contains between 1 and 5 product lines.
        item_count = rng.randint(1, 5)

        for _ in range(item_count):

            product = rng.choice(product_records)

            quantity = rng.randint(1, 5)

            unit_price = Decimal(
                str(product["unit_price"])
            )

            if not unit_price.is_finite() or unit_price <= 0:
                raise ValueError(
                    f"Invalid product price: {unit_price}"
                )

            # Calculate gross line revenue.
            gross_revenue = unit_price * quantity

            # Generate a discount between 0% and 20%.
            # 10000 basis points = 100%.
            discount_basis_points = rng.randint(0, 2000)

            discount_amount = (
                gross_revenue
                * Decimal(discount_basis_points)
                / Decimal(10000)
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            order_item = {
                "source_order_item_id": f"ITEM{item_number:09d}",
                "source_order_id": order["source_order_id"],
                "source_product_id": product["source_product_id"],
                "quantity": str(quantity),
                "unit_price": f"{unit_price:.2f}",
                "discount_amount": f"{discount_amount:.2f}",
            }

            order_items.append(order_item)

            item_number += 1

    return pd.DataFrame(order_items)



def generate_payments(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic ecommerce payment transactions.

    Payment generation rules:
    - Pending orders receive pending payments.
    - Cancelled orders receive failed payments.
    - Returned orders receive a completed payment and a refund.
    - Other valid orders receive a completed payment.
    - Some completed orders have a failed attempt before success.

    Each payment represents one transaction attempt or refund.

    Payment amounts are positive. Refunded amounts must be
    subtracted from completed payments during financial analysis.
    """

    required_order_columns = {
        "source_order_id",
        "order_date",
        "order_status",
    }

    required_item_columns = {
        "source_order_item_id",
        "source_order_id",
        "quantity",
        "unit_price",
        "discount_amount",
    }

    allowed_order_statuses = {
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled",
        "Returned",
    }

    missing_order_columns = (
        required_order_columns - set(orders.columns)
    )

    missing_item_columns = (
        required_item_columns - set(order_items.columns)
    )

    if missing_order_columns:
        raise ValueError(
            f"Orders DataFrame is missing columns: {missing_order_columns}"
        )

    if missing_item_columns:
        raise ValueError(
            f"Order items DataFrame is missing columns: {missing_item_columns}"
        )

    if orders.empty or order_items.empty:
        raise ValueError(
            "Orders and order items cannot be empty."
        )

    # Validate order identifiers.
    if orders["source_order_id"].isna().any():
        raise ValueError(
            "Order IDs cannot contain missing values."
        )

    if orders["source_order_id"].duplicated().any():
        raise ValueError(
            "Order IDs must be unique."
        )

    # Validate order item identifiers.
    if order_items["source_order_item_id"].isna().any():
        raise ValueError(
            "Order item IDs cannot contain missing values."
        )

    if order_items["source_order_item_id"].duplicated().any():
        raise ValueError(
            "Order item IDs must be unique."
        )

    if order_items["source_order_id"].isna().any():
        raise ValueError(
            "Order item references cannot contain missing values."
        )

    # Validate order statuses.
    if orders["order_status"].isna().any():
        raise ValueError(
            "Order statuses cannot contain missing values."
        )

    unsupported_statuses = (
        set(orders["order_status"].unique())
        - allowed_order_statuses
    )

    if unsupported_statuses:
        raise ValueError(
            f"Unsupported order statuses: {unsupported_statuses}"
        )

    rng = random.Random(seed)

    reference_date = date.fromisoformat(REFERENCE_DATE)

    order_records = orders.to_dict("records")
    item_records = order_items.to_dict("records")

    # Validate order dates before generating transactions.
    order_dates = {}

    for order in order_records:

        order_id = order["source_order_id"]

        try:
            order_date = date.fromisoformat(
                str(order["order_date"])
            )
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid order date for order {order_id}."
            ) from None

        if order_date > reference_date:
            raise ValueError(
                f"Order {order_id} has a date after the reference date."
            )

        order_dates[order_id] = order_date

    # Calculate each order's net amount from its order items.
    order_totals = {}

    for item in item_records:

        order_id = item["source_order_id"]

        # Safely convert financial and quantity values to Decimal.
        try:
            quantity = Decimal(str(item["quantity"]))
            unit_price = Decimal(str(item["unit_price"]))
            discount_amount = Decimal(str(item["discount_amount"]))

        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(
                f"Invalid numeric value for order {order_id}."
            ) from None

        # Validate quantity.
        if (
            not quantity.is_finite()
            or quantity <= 0
            or quantity != quantity.to_integral_value()
        ):
            raise ValueError(
                f"Quantity must be a positive whole number "
                f"for order {order_id}."
            )

        # Validate unit price.
        if not unit_price.is_finite() or unit_price <= 0:
            raise ValueError(
                f"Invalid unit price for order {order_id}."
            )

        # Validate discount.
        if (
            not discount_amount.is_finite()
            or discount_amount < 0
        ):
            raise ValueError(
                f"Invalid discount for order {order_id}."
            )

        gross_amount = quantity * unit_price

        if discount_amount > gross_amount:
            raise ValueError(
                f"Discount exceeds gross amount for order {order_id}."
            )

        net_amount = gross_amount - discount_amount

        order_totals[order_id] = (
            order_totals.get(order_id, Decimal("0.00"))
            + net_amount
        )

    # Every order must have at least one order item.
    order_ids = {
        order["source_order_id"]
        for order in order_records
    }

    item_order_ids = set(order_totals.keys())

    if order_ids != item_order_ids:
        raise ValueError(
            "Every order must have order items, and every "
            "order item must reference an existing order."
        )

    # Validate calculated order totals.
    for order_id, payment_amount in order_totals.items():

        if not payment_amount.is_finite() or payment_amount <= 0:
            raise ValueError(
                f"Order {order_id} has a non-positive payment amount."
            )

    payments = []

    payment_number = 1

    def create_payment(
        order_id: str,
        payment_method: str,
        payment_status: str,
        payment_date: date,
        payment_amount: Decimal,
    ) -> None:
        """Create one payment transaction record."""

        nonlocal payment_number

        payment = {
            "source_payment_id": f"PAY{payment_number:09d}",
            "source_order_id": order_id,
            "payment_method": payment_method,
            "payment_status": payment_status,
            "payment_date": payment_date.isoformat(),
            "payment_amount": f"{payment_amount:.2f}",
        }

        payments.append(payment)

        payment_number += 1

    def generate_payment_date(
        base_date: date,
        maximum_delay: int,
    ) -> date:
        """Generate a payment date without exceeding the reference date."""

        available_days = (
            reference_date - base_date
        ).days

        actual_delay = rng.randint(
            0,
            min(maximum_delay, available_days),
        )

        return base_date + timedelta(days=actual_delay)

    for order in order_records:

        order_id = order["source_order_id"]

        order_date = order_dates[order_id]

        order_status = order["order_status"]

        payment_amount = order_totals[order_id]

        payment_method = rng.choice(PAYMENT_METHODS)

        # Scenario 1: Order awaiting payment.
        if order_status == "Pending":

            payment_date = generate_payment_date(
                order_date,
                maximum_delay=2,
            )

            create_payment(
                order_id,
                payment_method,
                "Pending",
                payment_date,
                payment_amount,
            )

        # Scenario 2: Cancelled order.
        elif order_status == "Cancelled":

            payment_date = generate_payment_date(
                order_date,
                maximum_delay=2,
            )

            create_payment(
                order_id,
                payment_method,
                "Failed",
                payment_date,
                payment_amount,
            )

        # Scenario 3: Returned order.
        elif order_status == "Returned":

            completed_date = generate_payment_date(
                order_date,
                maximum_delay=2,
            )

            refund_date = generate_payment_date(
                completed_date,
                maximum_delay=14,
            )

            # Original successful payment.
            create_payment(
                order_id,
                payment_method,
                "Completed",
                completed_date,
                payment_amount,
            )

            # Separate refund transaction.
            create_payment(
                order_id,
                payment_method,
                "Refunded",
                refund_date,
                payment_amount,
            )

        # Scenario 4: Processing, shipped or delivered.
        elif order_status in {
            "Processing",
            "Shipped",
            "Delivered",
        }:

            # 90% successful immediately.
            # 10% failed attempt followed by successful retry.
            has_failed_attempt = rng.random() < 0.10

            if has_failed_attempt:

                failed_date = generate_payment_date(
                    order_date,
                    maximum_delay=2,
                )

                completed_date = generate_payment_date(
                    failed_date,
                    maximum_delay=2,
                )

                create_payment(
                    order_id,
                    payment_method,
                    "Failed",
                    failed_date,
                    payment_amount,
                )

                create_payment(
                    order_id,
                    payment_method,
                    "Completed",
                    completed_date,
                    payment_amount,
                )

            else:

                completed_date = generate_payment_date(
                    order_date,
                    maximum_delay=3,
                )

                create_payment(
                    order_id,
                    payment_method,
                    "Completed",
                    completed_date,
                    payment_amount,
                )

    return pd.DataFrame(payments)



def save_payments(
    payments: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Save payment transaction records to a CSV file."""

    if output_dir is None:
        output_dir = PROJECT_ROOT / RAW_DATA_DIR
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "payments.csv"

    payments.to_csv(
        output_file,
        index=False,
        encoding="utf-8",
    )

    return output_file


# ---------------------------------------------------------------------
# CSV saving utilities
# ---------------------------------------------------------------------

def save_customers(
    customers: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Save customer records to a CSV file."""

    if output_dir is None:
        output_dir = PROJECT_ROOT / RAW_DATA_DIR
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "customers.csv"

    customers.to_csv(
        output_file,
        index=False,
        encoding="utf-8",
    )

    return output_file


def save_products(
    products: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Save product records to a CSV file."""

    if output_dir is None:
        output_dir = PROJECT_ROOT / RAW_DATA_DIR
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "products.csv"

    products.to_csv(
        output_file,
        index=False,
        encoding="utf-8",
    )

    return output_file


def save_orders(
    orders: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Save order records to a CSV file."""

    if output_dir is None:
        output_dir = PROJECT_ROOT / RAW_DATA_DIR
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "orders.csv"

    orders.to_csv(
        output_file,
        index=False,
        encoding="utf-8",
    )

    return output_file


def save_order_items(
    order_items: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Save order-item records to a CSV file."""

    if output_dir is None:
        output_dir = PROJECT_ROOT / RAW_DATA_DIR
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "order_items.csv"

    order_items.to_csv(
        output_file,
        index=False,
        encoding="utf-8",
    )

    return output_file


# ---------------------------------------------------------------------
# Local execution
# ---------------------------------------------------------------------



if __name__ == "__main__":

    # Generate small datasets for initial testing.
    customer_data = generate_customers(count=10)
    product_data = generate_products(count=10)

    order_data = generate_orders(
        customers=customer_data,
        count=10,
    )

    order_item_data = generate_order_items(
        orders=order_data,
        products=product_data,
    )

    payment_data = generate_payments(
        orders=order_data,
        order_items=order_item_data,
    )

    # Save generated datasets.
    customer_file = save_customers(customer_data)
    product_file = save_products(product_data)
    order_file = save_orders(order_data)
    order_item_file = save_order_items(order_item_data)
    payment_file = save_payments(payment_data)

    # Display generation summary.
    print(f"Generated customers: {len(customer_data)}")
    print(f"Generated products: {len(product_data)}")
    print(f"Generated orders: {len(order_data)}")
    print(f"Generated order items: {len(order_item_data)}")
    print(f"Generated payments: {len(payment_data)}")

    print("\nGenerated files:")
    print(customer_file)
    print(product_file)
    print(order_file)
    print(order_item_file)
    print(payment_file)

    print("\nPayment preview:")
    print(payment_data.head(10))
