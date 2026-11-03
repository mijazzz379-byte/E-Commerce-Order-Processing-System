"""Report generation for processed orders."""

from order_processing import to_money, add_amounts


def generate_customer_report(processed_orders):
    """Revenue per customer (completed/paid orders only)."""
    customer_sales = {}
    for order in processed_orders:
        if order["status"] != "completed":
            continue
        customer = order["customer"]
        customer_sales[customer] = add_amounts(customer_sales.get(customer, 0), order["total"])
    return customer_sales


def generate_product_report(processed_orders, products):
    """Quantity sold per product_id (completed orders only), with the product name."""
    product_sales = {}
    for order in processed_orders:
        if order["status"] != "completed":
            continue
        for item in order["items"]:
            product_id = item["product_id"]
            name = products.get(product_id, {}).get("name", product_id)
            entry = product_sales.setdefault(product_id, {"name": name, "quantity": 0})
            entry["quantity"] += item["quantity"]
    return product_sales


def get_low_stock_products(products, threshold=10):
    """Names of products whose stock is at or below the threshold."""
    return [p["name"] for p in products.values() if p["stock"] <= threshold]


def get_top_customers(customer_sales):
    """All customers tied for the highest spend (sorted by name)."""
    if not customer_sales:
        return []
    highest = max(customer_sales.values())
    return sorted(name for name, amount in customer_sales.items() if amount == highest)


def get_top_selling_products(product_sales):
    """Names of all products tied for the highest quantity sold (sorted by name)."""
    if not product_sales:
        return []
    highest = max(entry["quantity"] for entry in product_sales.values())
    return sorted(entry["name"] for entry in product_sales.values() if entry["quantity"] == highest)


def get_ranked_customers(customer_sales):
    """Customers sorted by spend (high to low), then name."""
    return sorted(customer_sales.items(), key=lambda pair: (-pair[1], pair[0]))


def get_unique_customers(processed_orders):
    """Set of customers with at least one accepted (non-rejected) order."""
    return {o["customer"] for o in processed_orders if o["status"] != "rejected"}


def get_unique_categories(products):
    """Set of product categories."""
    return {p["category"] for p in products.values()}


def generate_sales_report(processed_orders, products):
    """Collect every number needed for the final report."""
    completed = [o for o in processed_orders if o["status"] == "completed"]
    customer_sales = generate_customer_report(processed_orders)
    product_sales = generate_product_report(processed_orders, products)

    return {
        "total_orders": len(processed_orders),
        "paid_orders": len(completed),
        "pending_orders": len([o for o in processed_orders if o["status"] == "pending"]),
        "rejected_orders": len([o for o in processed_orders if o["status"] == "rejected"]),
        "total_revenue": add_amounts(*[o["total"] for o in completed]),
        "total_discount": add_amounts(*[o["discount"] for o in completed]),
        "total_shipping": add_amounts(*[o["shipping"] for o in completed]),
        "top_customers": get_top_customers(customer_sales),
        "top_products": get_top_selling_products(product_sales),
        "low_stock_products": get_low_stock_products(products),
        "unique_customers": get_unique_customers(processed_orders),
        "unique_categories": get_unique_categories(products),
    }


def format_sales_report(report):
    """Return the report text in the format required by the assessment."""
    top_customer = ", ".join(report["top_customers"]) or "N/A"
    top_product = ", ".join(report["top_products"]) or "N/A"
    low_stock = [f"- {name}" for name in report["low_stock_products"]] or ["- None"]

    lines = [
        "========== SALES REPORT ==========",
        "",
        f"Total Orders: {report['total_orders']}",
        f"Paid Orders: {report['paid_orders']}",
        f"Pending Orders: {report['pending_orders']}",
        f"Rejected Orders: {report['rejected_orders']}",
        "",
        f"Total Revenue: ${report['total_revenue']:,.2f}",
        f"Total Discount: ${report['total_discount']:,.2f}",
        f"Total Shipping: ${report['total_shipping']:,.2f}",
        "",
        f"Top Customer: {top_customer}",
        f"Top Selling Product: {top_product}",
        "",
        "Low Stock Products:",
        *low_stock,
        "",
        "==================================",
    ]
    return "\n".join(lines)
