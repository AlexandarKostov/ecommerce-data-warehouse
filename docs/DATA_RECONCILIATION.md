# Data Reconciliation

## 1. Purpose

Dataset-level validation can establish that an individual row is well-formed, but it cannot prove that related datasets agree with one another. Reconciliation checks business consistency across orders, order items, and payments.

Implementation: `src/transformation/reconciliation/orders.py`

## 2. Order-item reconciliation

The reconciliation process checks that:

- An accepted order has at least one valid order item.
- Child records associated with a rejected parent order are not retained as valid.
- Order totals are calculated from accepted order items using decimal arithmetic.
- Invalid or orphaned child records are rejected with structured reasons.

## 3. Payment reconciliation

Payment records are checked against the associated order and calculated net order total. Reconciliation also checks that payment states make sense for the order's business status.

The current rules include:

| Order status | Expected payment behavior |
|---|---|
| Pending | Payment statuses are pending |
| Cancelled | Payment statuses are failed |
| Returned | Includes completed and refunded transactions; excludes pending and failed |
| Processing / Shipped / Delivered | At least one completed payment; only completed or failed attempts are allowed |

Payment amounts must reconcile with the expected net order total according to the implemented business rules.

## 4. Rejection behavior

Reconciliation preserves records that were already rejected by dataset-level validation. It also rejects otherwise well-formed records when cross-dataset relationships or business states are inconsistent.

The result separates valid and rejected orders, order items, and payments. Rejected counts represent physical records; issue counts represent individual reasons.

## 5. Tests

`tests/test_order_reconciliation.py` covers reconciliation behavior, including parent/child consistency, payment-state rules, amounts, and duplicate-order handling.

## 6. Future considerations

Before expanding reconciliation, define explicit policies for:

- Partial payments and split tender.
- Multiple successful captures.
- Partial refunds and multiple refund events.
- Currency conversion and multi-currency orders.
- Chargebacks and disputed transactions.
- Order edits after payment.
- Late-arriving or corrected source records.

These should be modeled as business rules rather than inferred from data alone.
