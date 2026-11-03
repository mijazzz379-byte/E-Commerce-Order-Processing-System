from data import products, orders
from order_processing import process_all_orders, demonstrate_legb
from reports import generate_sales_report, format_sales_report


def main():
    # Each demo run starts with its own inventory. Product fields are scalar,
    # so copying each product dictionary isolates stock updates.
    inventory = {product_id: dict(product) for product_id, product in products.items()}
    processed_orders = process_all_orders(orders, inventory)

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


if __name__ == "__main__":
    main()
