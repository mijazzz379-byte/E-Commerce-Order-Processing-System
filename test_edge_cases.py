"""Simple test runner (no classes, no external libraries). Run: python test_edge_cases.py"""

import unittest
from copy import deepcopy
from decimal import Decimal

from data import products as sample_products, orders as sample_orders
from order_processing import (
    calculate_discount, calculate_shipping, calculate_order_subtotal,
    validate_order, validate_products, process_order, process_all_orders, add_amounts,
    cancel_order,
)
from reports import generate_sales_report, format_sales_report, generate_customer_report, format_receipt
from storage import save_state, load_state, load_orders, load_products, export_results_csv


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


# ---- fixes from the second review
def test_duplicate_across_batches():
    products, seen = fresh_products(), {}
    order = make_order([item("P001", 2)], "ORD9")
    first = process_all_orders([order], products, seen)
    second = process_all_orders([deepcopy(order)], products, seen)
    assert first[0]["status"] == "completed"
    assert second[0]["status"] == "rejected" and "Duplicate" in second[0]["reason"]
    assert products["P001"]["stock"] == 8


def test_duplicate_across_process_order_calls():
    products, seen = fresh_products(), {}
    order = make_order([item("P001", 2)], "ORD9")
    assert process_order(order, products, seen)["status"] == "completed"
    assert process_order(order, products, seen)["status"] == "rejected"
    assert products["P001"]["stock"] == 8


def test_order_ids_are_normalised():
    products = fresh_products()
    orders = [make_order([item("P002", 1)], oid) for oid in ("ORD9", "ORD9 ", "ord9", " Ord9")]
    results = process_all_orders(orders, products)
    assert [r["status"] for r in results] == ["completed", "rejected", "rejected", "rejected"]
    assert products["P002"]["stock"] == 49


def test_pending_order_can_be_paid_once():
    products, seen = fresh_products(), {}
    pending = make_order([item("P002", 5)], "C", payment="pending")
    paid = make_order([item("P002", 5)], "c ", payment="paid")
    assert process_order(pending, products, seen)["status"] == "pending"
    assert products["P002"]["stock"] == 50
    assert process_order(paid, products, seen)["status"] == "completed"
    assert products["P002"]["stock"] == 45
    again = process_order(paid, products, seen)
    assert again["status"] == "rejected" and "Duplicate" in again["reason"]
    assert products["P002"]["stock"] == 45


def test_pending_twice_is_duplicate():
    products, seen = fresh_products(), {}
    pending = make_order([item("P002", 5)], "C", payment="pending")
    process_order(pending, products, seen)
    assert process_order(pending, products, seen)["status"] == "rejected"


def test_paid_order_must_match_pending_order():
    products, seen = fresh_products(), {}
    process_order(make_order([item("P002", 5)], "C", "Ali", "pending"), products, seen)
    other_items = process_order(make_order([item("P001", 1)], "C", "Ali"), products, seen)
    other_customer = process_order(make_order([item("P002", 5)], "C", "Zara"), products, seen)
    assert other_items["status"] == "rejected" and "does not match" in other_items["reason"]
    assert other_customer["status"] == "rejected"
    assert products["P001"]["stock"] == 10 and products["P002"]["stock"] == 50


def test_pending_in_one_batch_then_paid_in_next():
    products, seen = fresh_products(), {}
    process_all_orders([make_order([item("P003", 2)], "Z", payment="pending")], products, seen)
    results = process_all_orders([make_order([item("P003", 2)], "Z")], products, seen)
    assert results[0]["status"] == "completed" and products["P003"]["stock"] == 18


def test_bad_product_data_is_rejected():
    bad_products = [
        {"P1": {"name": "X", "price": "abc", "category": "C", "stock": 5}},
        {"P1": {"name": "X", "price": -25, "category": "C", "stock": 5}},
        {"P1": {"name": "X", "price": float("nan"), "category": "C", "stock": 5}},
        {"P1": {"name": "X", "price": True, "category": "C", "stock": 5}},
        {"P1": {"name": "X", "price": 5, "category": "C", "stock": "50"}},
        {"P1": {"name": "X", "price": 5, "category": "C", "stock": -1}},
        {"P1": {"name": "X", "price": 5, "category": "C", "stock": 2.5}},
        {"P1": {"name": "", "price": 5, "category": "C", "stock": 5}},
        {"P1": {"name": "X", "price": 5, "category": None, "stock": 5}},
        {"P1": {"name": "X", "price": 5, "stock": 5}},
        {"P1": "not a dict"},
    ]
    for bad in bad_products:
        for call in (lambda: validate_products(bad),
                     lambda: process_all_orders([make_order([item("P1", 1)])], bad),
                     lambda: process_order(make_order([item("P1", 1)]), bad)):
            try:
                call()
            except ValueError:
                continue
            raise AssertionError(f"{bad} should have raised ValueError")


def test_good_product_data_passes():
    validate_products(fresh_products())
    validate_products({})
    validate_products({"P1": {"name": "X", "price": 0, "category": "C", "stock": 0}})
    validate_products({"P1": {"name": "X", "price": 9.99, "category": "C", "stock": 3}})
    validate_products({"P1": {"name": "X", "price": Decimal("9.99"), "category": "C", "stock": 3}})


def test_customer_names_are_normalised():
    products = fresh_products()
    orders = [make_order([item("P002", 1)], "N1", "Ali"), make_order([item("P002", 1)], "N2", " ali "),
              make_order([item("P002", 1)], "N3", "ALI  ")]
    results = process_all_orders(orders, products)
    report = generate_sales_report(results, products)
    assert report["unique_customers"] == {"Ali"}
    assert list(generate_customer_report(results)) == ["Ali"]
    assert report["top_customers"] == ["Ali"]


def test_orders_must_be_a_list():
    for bad in (None, "ORD1", 42, {"order_id": "A"}):
        try:
            process_all_orders(bad, fresh_products())
        except TypeError as error:
            assert "orders must be a list" in str(error)
            continue
        raise AssertionError(f"{bad!r} should have raised TypeError")


def test_bad_processed_ids_rejected():
    try:
        process_order(make_order([item("P002", 1)]), fresh_products(), ["ORD1"])
    except TypeError:
        return
    raise AssertionError("a list for processed_ids should raise TypeError")


def test_rejected_orders_are_not_remembered():
    products, seen = fresh_products(), {}
    process_order(make_order([item("P001", 99)], "R1"), products, seen)
    assert seen == {}
    assert process_order(make_order([item("P001", 1)], "R1"), products, seen)["status"] == "completed"


def test_main_runs_twice_with_same_output():
    from contextlib import redirect_stdout
    from io import StringIO
    from main import main
    out = []
    for _ in range(2):
        buffer = StringIO()
        with redirect_stdout(buffer):
            main()
        out.append(buffer.getvalue())
    assert out[0] == out[1]


# ---- new features: cancel, receipt, save/load, CSV, command-line options
def test_cancel_completed_order_returns_stock():
    products, seen = fresh_products(), {}
    results = process_all_orders([make_order([item("P001", 2), item("P002", 3)], "K1")], products, seen)
    assert products["P001"]["stock"] == 8 and products["P002"]["stock"] == 47
    cancelled = cancel_order(" k1 ", products, seen, results)
    assert cancelled["status"] == "cancelled" and "stock returned" in cancelled["reason"]
    assert products["P001"]["stock"] == 10 and products["P002"]["stock"] == 50
    assert results[0]["status"] == "cancelled"


def test_cancel_pending_order_keeps_stock():
    products, seen = fresh_products(), {}
    results = process_all_orders([make_order([item("P002", 5)], "K2", payment="pending")], products, seen)
    assert cancel_order("K2", products, seen, results)["status"] == "cancelled"
    assert products["P002"]["stock"] == 50 and results[0]["status"] == "cancelled"


def test_cancel_twice_or_unknown_is_rejected():
    products, seen = fresh_products(), {}
    process_order(make_order([item("P002", 1)], "K3"), products, seen)
    assert cancel_order("K3", products, seen)["status"] == "cancelled"
    assert cancel_order("K3", products, seen)["status"] == "rejected"
    assert cancel_order("NOPE", products, seen)["status"] == "rejected"
    for bad in (None, "", "  ", 5):
        assert cancel_order(bad, products, seen)["status"] == "rejected"
    assert products["P002"]["stock"] == 50  # returned once only


def test_cancelled_id_cannot_be_reused():
    products, seen = fresh_products(), {}
    order = make_order([item("P002", 1)], "K4")
    process_order(order, products, seen)
    cancel_order("K4", products, seen)
    assert process_order(order, products, seen)["status"] == "rejected"
    assert products["P002"]["stock"] == 50


def test_cancelled_orders_leave_the_report():
    products, seen = fresh_products(), {}
    orders = [make_order([item("P002", 1)], "A", "Ali"), make_order([item("P003", 1)], "B", "Zara")]
    results = process_all_orders(orders, products, seen)
    cancel_order("B", products, seen, results)
    report = generate_sales_report(results, products)
    assert report["paid_orders"] == 1 and report["cancelled_orders"] == 1
    assert report["unique_customers"] == {"Ali"} and report["top_customers"] == ["Ali"]
    assert report["total_revenue"] == 45
    assert "Cancelled Orders: 1" in format_sales_report(report)


def test_report_format_unchanged_without_cancellations():
    products = fresh_products()
    report = generate_sales_report(process_all_orders(sample_orders, products), products)
    assert "Cancelled" not in format_sales_report(report)


def test_receipt_text():
    products = fresh_products()
    result = process_order(make_order([item("P001", 1), item("P002", 2)], "RC", "Ali"), products)
    text = format_receipt(result, products)
    assert "Laptop x 1 @ $1,200.00 = $1,200.00" in text and "Mouse x 2 @ $25.00 = $50.00" in text
    assert "Discount: -$187.50" in text and "Total:    $1,062.50" in text
    rejected = process_order(make_order([item("P001", 99)], "RJ"), products)
    assert format_receipt(rejected, products) == "Order RJ was rejected: Insufficient stock for P001"


def temp_path(name):
    import os, tempfile
    folder = tempfile.mkdtemp()
    return os.path.join(folder, name)


def test_save_and_load_state_keeps_duplicate_protection():
    products, seen = fresh_products(), {}
    process_all_orders([make_order([item("P001", 2)], "S1"),
                        make_order([item("P002", 5)], "S2", payment="pending")], products, seen)
    path = temp_path("state.json")
    save_state(path, products, seen)
    loaded_products, loaded_ids = load_state(path)
    assert loaded_products == products and loaded_ids.keys() == seen.keys()
    again = process_all_orders([make_order([item("P001", 2)], "s1")], loaded_products, loaded_ids)
    assert again[0]["status"] == "rejected" and loaded_products["P001"]["stock"] == 8
    paid = process_all_orders([make_order([item("P002", 5)], "S2")], loaded_products, loaded_ids)
    assert paid[0]["status"] == "completed" and loaded_products["P002"]["stock"] == 45
    assert cancel_order("S1", loaded_products, loaded_ids)["status"] == "cancelled"
    assert loaded_products["P001"]["stock"] == 10


def test_load_state_rejects_bad_files():
    cases = ["not json", "[]", '{"products": {}}',
             '{"products": {"P": {"name": "x", "price": "abc", "category": "c", "stock": 1}}, "processed_ids": {}}',
             '{"products": {}, "processed_ids": {"A": {"status": "weird", "signature": ["x", []]}}}',
             '{"products": {}, "processed_ids": {"A": 5}}']
    for text in cases:
        path = temp_path("bad.json")
        with open(path, "w") as file:
            file.write(text)
        try:
            load_state(path)
        except ValueError:
            continue
        raise AssertionError(f"{text!r} should have raised ValueError")


def test_load_orders_and_products():
    import json
    path = temp_path("orders.json")
    with open(path, "w") as file:
        json.dump(sample_orders, file)
    assert load_orders(path) == sample_orders
    with open(path, "w") as file:
        json.dump({"a": 1}, file)
    try:
        load_orders(path)
    except ValueError:
        pass
    else:
        raise AssertionError("an object is not a list of orders")
    with open(path, "w") as file:
        json.dump(sample_products, file)
    assert load_products(path) == sample_products


def test_export_csv():
    import csv
    products = fresh_products()
    results = process_all_orders(sample_orders, products)
    path = temp_path("out.csv")
    export_results_csv(path, results)
    with open(path, newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["order_id"] for row in rows] == ["ORD001", "ORD002", "ORD003"]
    assert rows[0]["total"] == "1062.50" and rows[2]["status"] == "pending"


def run_main(args):
    from contextlib import redirect_stdout
    from io import StringIO
    from main import main
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = main(args)
    return code, buffer.getvalue()


def test_main_state_file_blocks_second_run():
    state = temp_path("state.json")
    code, first = run_main(["--state", state])
    assert code == 0 and "ORD001: completed" in first
    code, second = run_main(["--state", state])
    assert code == 0 and "ORD001: rejected - Duplicate order ID: ORD001" in second
    assert "Paid Orders: 0" in second
    _, saved_ids = load_state(state)
    assert saved_ids["ORD001"]["status"] == "completed"


def test_main_with_files_and_csv():
    import json
    orders_path, products_path, csv_path = temp_path("o.json"), temp_path("p.json"), temp_path("r.csv")
    with open(orders_path, "w") as file:
        json.dump([make_order([item("X1", 2)], "F1", "Sam")], file)
    with open(products_path, "w") as file:
        json.dump({"X1": {"name": "Widget", "price": 10, "category": "Misc", "stock": 5}}, file)
    code, out = run_main(["--orders", orders_path, "--products", products_path, "--csv", csv_path])
    assert code == 0 and "F1: completed" in out and "Total Revenue: $40.00" in out
    with open(csv_path) as file:
        assert "F1,Sam,completed" in file.read()


def test_main_reports_file_errors_without_crashing():
    code, out = run_main(["--orders", temp_path("missing.json")])
    assert code == 1 and out.startswith("Error:")
    bad = temp_path("bad.json")
    with open(bad, "w") as file:
        file.write("{oops")
    code, out = run_main(["--orders", bad])
    assert code == 1 and "not valid JSON" in out
    with open(bad, "w") as file:
        file.write('{"X": {"name": "x", "price": -1, "category": "c", "stock": 1}}')
    code, out = run_main(["--products", bad])
    assert code == 1 and "price" in out


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


def load_tests(loader, tests, pattern):
    """Lets `python -m unittest` find the plain test functions above."""
    suite = unittest.TestSuite()
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            suite.addTest(unittest.FunctionTestCase(func, description=name))
    return suite


if __name__ == "__main__":
    raise SystemExit(run_all())
