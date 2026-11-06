# Data Validation

## 1. Purpose

Validation protects the warehouse from malformed source values, missing references, invalid business attributes, and inconsistent financial values. The validators are implemented as Python functions that return structured accepted and rejected records rather than writing to the database directly.

## 2. Validation result model

Module: `src/transformation/validation_result.py`

The result model contains:

- `valid_records`: records that passed the validator.
- `rejected_records`: records that failed one or more rules.
- `valid_count`, `rejected_count`, `total_count`, and `issue_count`.
- `rejection_reasons`: structured issue dictionaries containing a code, field, and message.

Validation is positional and does not mutate the input DataFrame. A record can have multiple issues.

## 3. Dataset validators

| Dataset | Module | Main rules |
|---|---|---|
| Customers | `validation/customers.py` | Required and unique source customer ID; required email; basic email format |
| Products | `validation/products.py` | Required and unique product ID; required product name; valid nonnegative price; nullable valid cost; nonnegative whole stock quantity |
| Orders | `validation/orders.py` | Required and unique order ID; valid customer reference; strict date format; no future order date relative to configured reference date; supported order status |
| Order items | `validation/order_items.py` | Required and unique item ID; valid order and product references; positive whole quantity; positive finite unit price; nonnegative discount not exceeding gross line value |
| Payments | `validation/payments.py` | Required and unique payment ID; valid order reference; supported payment method/status; valid payment date and chronology; positive finite amount; amount matching expected net order total |

Exact rule definitions and issue codes are maintained in the validator modules and their tests.

## 4. Cross-dataset dependencies

The validation pipeline validates customers and products first, then uses accepted identifiers to validate orders and order items. It calculates expected order totals from accepted order items and supplies the necessary order dates/totals to payment validation.

This prevents child records from being treated as valid when their referenced parent records have already failed validation.

## 5. Financial precision

Financial values are parsed and calculated using `Decimal`, not binary floating-point arithmetic. Order totals are derived from accepted order-item quantities, prices, and discounts.

## 6. Rejected record persistence

Module: `src/loading/rejected_records_loader.py`

The loader:

- Supports the five configured staging tables.
- Requires staging identifiers and structured rejection reasons for nonempty rejected datasets.
- Validates that staging IDs are present and unique.
- Stores the source record ID where available.
- Serializes raw source fields and issue reasons to JSON.
- Handles date/datetime, Decimal, and NumPy scalar serialization.
- Excludes staging metadata such as `staging_id`, `etl_run_id`, and `loaded_at` from the raw source payload.
- Does not own the database transaction; the caller controls commit/rollback.

One database row represents one rejected physical staging record. Multiple issues for the same record are stored together in the JSON reasons array.

## 7. Quality data

The project includes separate quality datasets under `data/quality/` and generation/injection modules. These are intended for controlled testing of duplicate identifiers, missing values, invalid numeric values, and invalid references.

Keep clean source data under `data/raw/` separate from intentionally corrupted quality data.

## 8. Known scope boundaries

- Validation is implemented and covered by automated tests.
- The validation pipeline is implemented and has unit-level tests.
- A controlled MySQL integration test for rejection persistence and final audit status remains pending.
- Validation rules should be extended only when supported by explicit business requirements and corresponding tests.
