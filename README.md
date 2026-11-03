# E-Commerce Order Processing System

Core order-processing logic for a small e-commerce platform, written in plain Python
(functions only: no classes, no external libraries, no database).

## How to run

```
python main.py              # process the sample orders and print the sales report
python test_edge_cases.py   # run all tests (30 checks)
```

Requires Python 3.8+.

## Review changes

The original ZIP passed its 25 tests and produced the correct assessment sample
report. One additional repeat-run issue was reproduced: calling `main()` twice
in the same interpreter deducted stock twice from the imported starter data.
`main()` now copies the inventory for each demo run and reports on that copy.
The processing functions still update the inventory supplied by their caller,
as required by the assessment.

Five added tests cover repeat-run isolation, disabling shipping on a chargeable
order, shipping eligibility before discount, exclusion of pending/rejected
orders from report totals, and avoiding partial stock deduction on rejection.
The original shipping-option test used an order already eligible for free
shipping, so it could not detect an ignored `include_shipping=False` option.

`decimal` and `copy` are Python standard-library modules, not external packages.
No user-defined classes or external dependencies are used. Whether these modules
were covered in the intern's lessons cannot be established from the assessment.
The test for captured console output also uses standard-library `contextlib`
and `io`.

## Files

| File | Purpose |
|------|---------|
| `data.py` | Starter products and orders |
| `order_processing.py` | Validation, subtotal, discount, shipping, order processing, LEGB demo |
| `reports.py` | Customer, product and sales reports and the report formatter |
| `main.py` | Runs everything (under `if __name__ == "__main__":`) |
| `test_edge_cases.py` | Tests for business rules and every required edge case |

## Business rules

- **Discount:** subtotal >= $1,000 -> 15%, >= $500 -> 10%, >= $200 -> 5%, otherwise 0%.
- **Shipping:** free when subtotal >= $500, otherwise $20.
- **Total** = subtotal - discount + shipping.
- **Revenue** counts only `paid` orders. `pending` orders are priced but not counted as revenue.
- **Stock** is reduced only for paid orders that passed validation.
- **Rejected** orders: unknown product, quantity that is not a positive whole number,
  insufficient stock (all lines of the same product are added together), no items,
  invalid payment status, missing `order_id` / `customer`, malformed order, or a repeated `order_id`.

## Options (`**kwargs`)

```python
process_order(order, products, apply_discount=False, include_shipping=False)
```

Unknown option names (e.g. a typo like `apply_discout`) or non-boolean values raise `TypeError`.

## Assumptions

- Low stock means stock **<= 10** (the assignment does not give a number; change `threshold` in `get_low_stock_products`).
- Top customer is ranked by revenue from paid orders; ties list every tied customer. Ties for top-selling product list every tied product by name.
- A repeated `order_id` is rejected, so stock is never deducted twice.
- Money uses `Decimal` (standard library) with half-up rounding, so there are no float errors like `150.67499999999998`.

## Sample output

```
========== SALES REPORT ==========

Total Orders: 3
Paid Orders: 2
Pending Orders: 1
Rejected Orders: 0

Total Revenue: $1,510.00
Total Discount: $210.00
Total Shipping: $20.00

Top Customer: Ali
Top Selling Product: Keyboard, Mouse

Low Stock Products:
- Laptop

==================================
```
