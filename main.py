import argparse
import json
import os

from data import products, orders
from order_processing import process_all_orders, demonstrate_legb
from reports import generate_sales_report, format_sales_report
from storage import (load_orders, load_products, load_state, save_state,
                     export_results_csv)


def build_parser():
    parser = argparse.ArgumentParser(description="E-Commerce Order Processing System")
    parser.add_argument("--orders", help="JSON file with a list of orders (default: sample orders)")
    parser.add_argument("--products", help="JSON file with the products (default: sample products)")
    parser.add_argument("--state", help="JSON file that remembers stock and processed order IDs between runs")
    parser.add_argument("--csv", help="write one row per processed order to this CSV file")
    return parser


def main(argv=()):
    """Run the demo. Returns 0 on success, 1 on a file or data error."""
    args = build_parser().parse_args(list(argv))

    try:
        order_list = load_orders(args.orders) if args.orders else orders
        if args.state and os.path.exists(args.state):
            inventory, processed_ids = load_state(args.state)
        else:
            # Each run starts with its own inventory so the sample data is never changed.
            source = load_products(args.products) if args.products else products
            inventory = {product_id: dict(product) for product_id, product in source.items()}
            processed_ids = {}  # remembers order IDs so an order can't be processed twice

        processed_orders = process_all_orders(order_list, inventory, processed_ids)

        if args.state:
            save_state(args.state, inventory, processed_ids)
        if args.csv:
            export_results_csv(args.csv, processed_orders)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"Error: {error}")
        return 1

    for order in processed_orders:
        print(f"{order['order_id']}: {order['status']} - {order['reason']}")

    report = generate_sales_report(processed_orders, inventory)
    print()
    print(format_sales_report(report))

    print("\nUnique Customers:", ", ".join(sorted(report["unique_customers"])))
    print("Unique Categories:", ", ".join(sorted(report["unique_categories"])))

    print("\nLEGB Demonstration:")
    for scope, value in demonstrate_legb().items():
        print(f"  {scope}: {value}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
