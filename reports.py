"""Report generation for processed orders."""

from order_processing import add_amounts, normalize_name, to_money


def generate_customer_report(processed_orders):
    """Revenue per customer (completed/paid orders only)."""
    totals = {}
    display_names = {}  # 'Ali' and ' ali ' are one customer; keep the first spelling seen
    for order in processed_orders:
        if order["status"] != "completed":
            continue
        key = normalize_name(order["customer"])
        display_names.setdefault(key, order["customer"])
        totals[key] = add_amounts(totals.get(key, 0), order["total"])
    return {display_names[key]: amount for key, amount in totals.items()}


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
    """Set of customers with at least one completed or pending order (not rejected or cancelled)."""
    names = {}
    for order in processed_orders:
        if order["status"] in ("completed", "pending"):
            names.setdefault(normalize_name(order["customer"]), order["customer"])
    return set(names.values())


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
        "cancelled_orders": len([o for o in processed_orders if o["status"] == "cancelled"]),
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
        *([f"Cancelled Orders: {report['cancelled_orders']}"] if report.get("cancelled_orders") else []),
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


def format_receipt(result, products):
    """A printable receipt for one processed order record."""
    if result["status"] == "rejected":
        return f"Order {result['order_id']} was rejected: {result['reason']}"

    lines = [
        f"===== RECEIPT: {result['order_id']} =====",
        f"Customer: {result['customer']}",
        f"Status: {result['status']}",
        "",
    ]
    for entry in result["items"]:
        product = products.get(entry["product_id"])
        if product is None:
            lines.append(f"{entry['product_id']} x {entry['quantity']}")
            continue
        price = to_money(product["price"])
        lines.append(f"{product['name']} x {entry['quantity']} @ ${price:,.2f} = ${price * entry['quantity']:,.2f}")
    lines.append("")
    lines.append(f"Subtotal: ${result['subtotal']:,.2f}")
    if result["discount"]:
        lines.append(f"Discount: -${result['discount']:,.2f}")
    lines.append(f"Shipping: ${result['shipping']:,.2f}")
    lines.append(f"Total:    ${result['total']:,.2f}")
    return "\n".join(lines)
