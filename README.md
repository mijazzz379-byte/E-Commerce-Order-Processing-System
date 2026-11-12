# E-Commerce Order Processing System

Core order-processing logic for a small e-commerce platform, written in plain Python
(functions only: no classes, no external libraries, no database).

## How to run

```
python main.py              # process the sample orders and print the sales report
python test_edge_cases.py   # run all 58 checks; pytest also discovers them when installed
```

Optional command-line options for `main.py`:

```
python main.py --orders my_orders.json      # use your own orders (a JSON list)
python main.py --products my_products.json  # use your own products (a JSON object)
python main.py --state state.json           # remember stock and order IDs between runs
python main.py --csv results.csv            # save one row per order to a CSV file
```

With `--state`, running the same orders a second time rejects them as duplicates instead of
deducting stock again. File problems (missing file, invalid JSON, bad product data) print
`Error: ...` and exit with code 1 instead of crashing.

Requires Python 3.8+.

## What changed

- **Duplicate orders are blocked across calls.** Pass one `processed_ids` dictionary to
  `process_order` / `process_all_orders` and an order can never be processed twice, even in
  separate calls. Order IDs ignore spaces and capitals (`"ORD9"`, `"ORD9 "`, `"ord9"` are the same order).
- **A pending order can be paid later, exactly once.** Process it as `pending`, then send it again as
  `paid` with the same ID, customer and items. A second payment is rejected as a duplicate.
- **Product data is validated** by `validate_products()` (name and category are text, price is a number
  that is not negative, stock is a whole number that is not negative). Bad data raises `ValueError` with every problem listed.
- **Customer names are cleaned** (`"Ali"` and `" ali "` count as one customer in the report).
- `process_all_orders` raises a clear `TypeError` if `orders` is not a list.
- **Cancel an order:** `cancel_order(order_id, products, processed_ids, processed_orders)` cancels a pending
  or completed order. A completed order's stock is returned, the order disappears from report totals, and a
  cancelled ID can't be used again.
- **Receipts:** `format_receipt(result, products)` prints a receipt with items, discount, shipping and total.
- **Save and load:** `storage.py` saves and loads the inventory and processed IDs (`save_state` / `load_state`),
  loads orders and products from JSON files, and exports results to CSV.
- **Command-line options** for `main.py` (see "How to run").
- Tests: 58 checks. They run with `python test_edge_cases.py`, `python -m unittest` or `pytest`.

## Files

| File | Purpose |
|------|---------|
| `data.py` | Starter products and orders |
| `order_processing.py` | Validation, subtotal, discount, shipping, order processing, LEGB demo |
| `reports.py` | Customer, product and sales reports, the report formatter and receipts |
| `storage.py` | Save/load state, load orders and products from JSON, export CSV |
| `main.py` | Runs everything, with optional command-line options (under `if __name__ == "__main__":`) |
| `test_edge_cases.py` | Tests for business rules and every required edge case |

## Business rules

- **Discount:** subtotal >= $1,000 -> 15%, >= $500 -> 10%, >= $200 -> 5%, otherwise 0%.
- **Shipping:** free when subtotal >= $500, otherwise $20.
- **Total** = subtotal - discount + shipping.
- **Revenue** counts only `paid` orders (cancelled orders are not counted). `pending` orders are priced but not counted as revenue.
- **Stock** is reduced only for paid orders that passed validation.
- **Rejected** orders: unknown product, quantity that is not a positive whole number,
  insufficient stock (all lines of the same product are added together), no items,
  invalid payment status, missing `order_id` / `customer`, malformed order, or a repeated `order_id`
  (a pending order may be paid once later; see below).

## Options (`**kwargs`)

```python
process_order(order, products, apply_discount=False, include_shipping=False)
```

## Stopping duplicate orders

```python
processed_ids = {}                                   # keep this alongside your inventory
process_all_orders(batch_1, inventory, processed_ids)
process_all_orders(batch_2, inventory, processed_ids)   # repeats from batch_1 are rejected
```

To cancel an order:

```python
cancel_order("ORD001", inventory, processed_ids, processed_orders)  # stock is returned
```

If you don't pass `processed_ids`, `process_all_orders` still rejects repeats inside that one batch,
but `process_order` treats every call on its own.

Unknown option names (e.g. a typo like `apply_discout`) or non-boolean values raise `TypeError`.

## Assumptions

- The report layout is unchanged, except that a `Cancelled Orders:` line appears when at least one order was cancelled.
- Saved JSON files store prices as plain numbers (a `Decimal` such as 9.99 is saved as 9.99).
- Low stock means stock **<= 10** (the assignment does not give a number; change `threshold` in `get_low_stock_products`).
- Top customer is ranked by revenue from paid orders; ties list every tied customer. Ties for top-selling product list every tied product by name.
- A repeated `order_id` is rejected, so stock is never deducted twice. A paid order may reuse the ID of a pending order only if the customer and items are the same.
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
