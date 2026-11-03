"""Simple test runner (no classes, no external libraries). Run: python test_edge_cases.py"""

from copy import deepcopy
from decimal import Decimal

from data import products as sample_products, orders as sample_orders
from order_processing import (
    calculate_discount, calculate_shipping, calculate_order_subtotal,
    validate_order, process_order, process_all_orders, add_amounts,
)
from reports import generate_sales_report, format_sales_report


def fresh_products():
    return deepcopy(sample_products)


def make_order(items, order_id="T1", customer="Test", payment="paid"):
    return {"order_id": order_id, "customer": customer, "items": items, "payment_status": payment}


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


# ---- pricing rules
def test_discount_tiers():
    assert calculate_discount(1000) == Decimal("150.00")
    assert calculate_discount(999.99) == Decimal("100.00")
    assert calculate_discount(500) == Decimal("50.00")
    assert calculate_discount(200) == Decimal("10.00")
    assert calculate_discount(199.99) == Decimal("0.00")
    assert calculate_discount(1004.50) == Decimal("150.68")  # half-up, no float noise


def test_shipping():
    assert calculate_shipping(500) == 0
    assert calculate_shipping(499.99) == 20


def test_subtotal():
    assert calculate_order_subtotal(sample_orders[0], sample_products) == Decimal("1250.00")


def test_add_amounts_args():
    assert add_amounts() == 0
    assert add_amounts(1, 2.5, 3) == Decimal("6.50")


# ---- required edge cases
def check_rejected(order, products, text):
    ok, message = validate_order(order, products)
    assert not ok and text in message, message
    result = process_order(order, products)
    assert result["status"] == "rejected"


def test_unknown_product():
    check_rejected(make_order([item("P999", 1)]), fresh_products(), "Unknown product")


def test_zero_quantity():
    check_rejected(make_order([item("P001", 0)]), fresh_products(), "Invalid quantity")


def test_negative_quantity():
    check_rejected(make_order([item("P001", -2)]), fresh_products(), "Invalid quantity")


def test_quantity_over_stock():
    check_rejected(make_order([item("P001", 11)]), fresh_products(), "Insufficient stock")


def test_no_items():
    check_rejected(make_order([]), fresh_products(), "no items")


def test_invalid_payment_status():
    check_rejected(make_order([item("P001", 1)], payment="refunded"), fresh_products(), "payment")


def test_empty_products():
    check_rejected(make_order([item("P001", 1)]), {}, "Unknown product")


def test_empty_orders_list():
    products = fresh_products()
    results = process_all_orders([], products)
    report = generate_sales_report(results, products)
    assert report["total_orders"] == 0 and report["total_revenue"] == 0
    assert "Top Customer: N/A" in format_sales_report(report)


def test_same_customer_multiple_orders():
    products = fresh_products()
    orders = [make_order([item("P002", 2)], "A1", "Ali"), make_order([item("P003", 1)], "A2", "Ali")]
    results = process_all_orders(orders, products)
    report = generate_sales_report(results, products)
    assert report["top_customers"] == ["Ali"] and report["unique_customers"] == {"Ali"}


def test_tie_top_products():
    products = fresh_products()
    results = process_all_orders([make_order([item("P002", 2), item("P003", 2)])], products)
    assert generate_sales_report(results, products)["top_products"] == ["Keyboard", "Mouse"]


def test_tie_top_customers():
    products = fresh_products()
    orders = [make_order([item("P001", 1)], "B1", "Ali"), make_order([item("P001", 1)], "B2", "Zara")]
    results = process_all_orders(orders, products)
    assert generate_sales_report(results, products)["top_customers"] == ["Ali", "Zara"]


def test_no_low_stock():
    products = {"P1": {"name": "X", "price": 5, "category": "C", "stock": 100}}
    report = generate_sales_report([], products)
    assert report["low_stock_products"] == []
    assert "- None" in format_sales_report(report)


# ---- bugs found in code review
def test_combined_stock_check():
    products = fresh_products()
    check_rejected(make_order([item("P001", 6), item("P001", 6)]), products, "Insufficient stock")
    assert products["P001"]["stock"] == 10


def test_bad_quantity_types():
    for bad in (True, 1.5, "2", None):
        check_rejected(make_order([item("P002", bad)]), fresh_products(), "Invalid quantity")


def test_missing_fields_do_not_crash():
    products = fresh_products()
    for order in ({"items": [item("P002", 1)], "payment_status": "paid"},
                  {"order_id": "X", "customer": "A", "items": [item("P002", 1)]},
                  {"order_id": "X", "customer": "A", "payment_status": "paid"},
                  {"order_id": "X", "customer": "A", "payment_status": "paid", "items": [{"quantity": 1}]},
                  None, "not an order", 42):
        assert process_order(order, products)["status"] == "rejected"


def test_duplicate_order_id():
    products = fresh_products()
    order = make_order([item("P002", 2)], "DUP")
    results = process_all_orders([order, deepcopy(order)], products)
    assert [r["status"] for r in results] == ["completed", "rejected"]
    assert products["P002"]["stock"] == 48


def test_unknown_option_rejected():
    for bad in ({"apply_discout": False}, {"apply_discount": "no"}):
        try:
            process_order(sample_orders[0], fresh_products(), **bad)
        except TypeError:
            continue
        raise AssertionError(f"{bad} should have raised TypeError")


def test_options_work():
    order = make_order([item("P001", 1)])
    assert process_order(order, fresh_products(), apply_discount=False)["discount"] == 0
    assert process_order(order, fresh_products(), include_shipping=False)["shipping"] == 0
    assert process_order(order, fresh_products())["total"] == Decimal("1020.00")


def test_stock_rules():
    products = fresh_products()
    process_order(make_order([item("P002", 5)], payment="pending"), products)
    process_order(make_order([item("P002", 500)]), products)
    assert products["P002"]["stock"] == 50  # pending and rejected: no change
    process_order(make_order([item("P002", 5)]), products)
    assert products["P002"]["stock"] == 45


def test_items_are_copied():
    order = make_order([item("P002", 1)])
    result = process_order(order, fresh_products())
    result["items"][0]["quantity"] = 99
    assert order["items"][0]["quantity"] == 1


def test_sample_report():
    products = fresh_products()
    results = process_all_orders(sample_orders, products)
    report = generate_sales_report(results, products)
    assert (report["total_revenue"], report["total_discount"], report["total_shipping"]) == (
        Decimal("1510.00"), Decimal("210.00"), Decimal("20.00"))
    assert (report["paid_orders"], report["pending_orders"], report["rejected_orders"]) == (2, 1, 0)


def test_main_keeps_starter_inventory():
    from contextlib import redirect_stdout
    from io import StringIO
    from main import main

    before = deepcopy(sample_products)
    first, second = StringIO(), StringIO()
    with redirect_stdout(first):
        main()
    assert sample_products == before
    with redirect_stdout(second):
        main()
    assert sample_products == before
    assert first.getvalue() == second.getvalue()


def test_shipping_option_below_free_threshold():
    order = make_order([item("P002", 1)])
    normal = process_order(order, fresh_products())
    no_shipping = process_order(order, fresh_products(), include_shipping=False)
    assert normal["shipping"] == 20 and normal["total"] == 45
    assert no_shipping["shipping"] == 0 and no_shipping["total"] == 25


def test_shipping_uses_subtotal_before_discount():
    result = process_order(make_order([item("P002", 20)]), fresh_products())
    assert result["subtotal"] == 500
    assert result["discount"] == 50
    assert result["shipping"] == 0 and result["total"] == 450


def test_pending_and_rejected_excluded_from_report_totals():
    products = fresh_products()
    orders = [make_order([item("P003", 3)], "PENDING", payment="pending"),
              make_order([item("P002", 1)], "PAID"),
              make_order([item("P004", 99)], "REJECTED")]
    results = process_all_orders(orders, products)
    report = generate_sales_report(results, products)
    assert (report["paid_orders"], report["pending_orders"], report["rejected_orders"]) == (1, 1, 1)
    assert (report["total_revenue"], report["total_discount"], report["total_shipping"]) == (45, 0, 20)
    assert report["top_products"] == ["Mouse"]
    assert products["P003"]["stock"] == 20 and products["P004"]["stock"] == 15


def test_rejected_order_does_not_partially_deduct_stock():
    products = fresh_products()
    before = deepcopy(products)
    result = process_order(make_order([item("P002", 1), item("P001", 11)]), products)
    assert result["status"] == "rejected"
    assert products == before


def run_all():
    tests = [(name, func) for name, func in globals().items()
             if name.startswith("test_") and callable(func)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"PASS  {name}")
        except Exception as error:  # report every failure instead of stopping
            failed += 1
            print(f"FAIL  {name}: {error!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(run_all())
