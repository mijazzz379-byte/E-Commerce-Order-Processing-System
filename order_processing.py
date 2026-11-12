"""Order validation, pricing and processing logic (no classes, no globals needed)."""

from decimal import Decimal, ROUND_HALF_UP


# ---------------------------------------------------------------- money helpers
def to_money(value):
    """Convert a number to a Decimal rounded to 2 places (half-up)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_id(order_id):
    """Order IDs are compared without spaces and ignoring case: ' ord9 ' == 'ORD9'."""
    return order_id.strip().upper()


def clean_name(name):
    """Trim the name and collapse repeated spaces (keeps the original capitals)."""
    return " ".join(name.split())


def normalize_name(name):
    """Key used to decide that 'Ali' and ' ali ' are the same customer."""
    return clean_name(name).casefold()


def add_amounts(*amounts):
    """*args helper: add any number of money amounts (used for subtotals and totals)."""
    total = Decimal("0.00")
    for amount in amounts:
        total += to_money(amount)
    return to_money(total)


# ---------------------------------------------------------------- pricing rules
def make_discount_calculator(tiers):
    """Closure: build a discount function from (minimum_subtotal, percent) tiers.

    `tiers` is remembered by `calculator` from the enclosing scope (the E in LEGB).
    """

    def calculator(subtotal):
        subtotal = to_money(subtotal)
        for minimum, percent in tiers:
            if subtotal >= minimum:
                return to_money(subtotal * percent / 100)
        return to_money(0)

    return calculator


def calculate_discount(subtotal):
    """>= 1000 -> 15%, >= 500 -> 10%, >= 200 -> 5%, otherwise 0%."""
    calculator = make_discount_calculator(((1000, 15), (500, 10), (200, 5)))
    return calculator(subtotal)


def calculate_shipping(subtotal):
    """Free shipping from $500, otherwise $20."""
    if to_money(subtotal) >= 500:
        return to_money(0)
    return to_money(20)


def calculate_order_subtotal(order, products):
    """Sum of price x quantity for every item."""
    line_totals = [
        to_money(products[item["product_id"]]["price"]) * item["quantity"]
        for item in order["items"]
    ]
    return add_amounts(*line_totals)


# ---------------------------------------------------------------- validation
def is_valid_price(price):
    """A price must be a finite number (not bool or str) that is not negative."""
    if isinstance(price, bool) or not isinstance(price, (int, float, Decimal)):
        return False
    amount = Decimal(str(price))
    return amount.is_finite() and amount >= 0


def is_valid_stock(stock):
    """Stock must be a whole number (not bool, float or str) that is not negative."""
    return isinstance(stock, int) and not isinstance(stock, bool) and stock >= 0


def validate_products(products):
    """Check the product data once. Raises ValueError listing every problem found."""
    if not isinstance(products, dict):
        raise TypeError("products must be a dictionary")

    problems = []
    for product_id, product in products.items():
        if not isinstance(product, dict):
            problems.append(f"{product_id}: product must be a dictionary")
            continue
        for field in ("name", "category"):
            value = product.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{product_id}: {field} must be a non-empty string")
        if not is_valid_price(product.get("price")):
            problems.append(f"{product_id}: price must be a number that is not negative")
        if not is_valid_stock(product.get("stock")):
            problems.append(f"{product_id}: stock must be a whole number that is not negative")

    if problems:
        raise ValueError("Invalid product data: " + "; ".join(problems))


def is_valid_quantity(quantity):
    """A quantity must be a real int (not bool, float or str) and > 0."""
    return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0


def validate_order(order, products):
    """Return (True, message) or (False, reason). Never raises for bad input."""
    if not isinstance(order, dict):
        return False, "Order must be a dictionary"

    order_id = order.get("order_id")
    if not isinstance(order_id, str) or not order_id.strip():
        return False, "Missing or invalid order_id"

    customer = order.get("customer")
    if not isinstance(customer, str) or not customer.strip():
        return False, "Missing or invalid customer"

    if order.get("payment_status") not in ("paid", "pending"):
        return False, "Invalid payment status"

    items = order.get("items")
    if not isinstance(items, list) or not items:
        return False, "Order has no items"

    # Add up the quantity per product so several lines of the same product
    # are checked against stock together.
    requested = {}
    for item in items:
        if not isinstance(item, dict):
            return False, "Each item must be a dictionary"

        product_id = item.get("product_id")
        if not isinstance(product_id, str) or product_id not in products:
            return False, f"Unknown product ID: {product_id}"

        quantity = item.get("quantity")
        if not is_valid_quantity(quantity):
            return False, f"Invalid quantity for {product_id}"

        requested[product_id] = requested.get(product_id, 0) + quantity

    for product_id, quantity in requested.items():
        if quantity > products[product_id]["stock"]:
            return False, f"Insufficient stock for {product_id}"

    return True, "Order is valid"


# ---------------------------------------------------------------- processing
def check_options(options):
    """Reject misspelled or non-boolean options instead of silently ignoring them."""
    allowed = ("apply_discount", "include_shipping")
    unknown = [name for name in options if name not in allowed]
    if unknown:
        raise TypeError(f"Unknown option(s): {', '.join(unknown)}. Allowed: {', '.join(allowed)}")
    for name, value in options.items():
        if not isinstance(value, bool):
            raise TypeError(f"Option '{name}' must be True or False")


def make_result(order, status, reason, subtotal=0, discount=0, shipping=0, total=0, items=None):
    """Build a processed-order record (safe even when the order is malformed)."""
    is_dict = isinstance(order, dict)
    order_id = order.get("order_id") if is_dict else None
    customer = order.get("customer") if is_dict else None
    return {
        "order_id": order_id.strip() if isinstance(order_id, str) else order_id,
        "customer": clean_name(customer) if isinstance(customer, str) else customer,
        "status": status,
        "reason": reason,
        "subtotal": to_money(subtotal),
        "discount": to_money(discount),
        "shipping": to_money(shipping),
        "total": to_money(total),
        "items": items if items is not None else [],
    }


def order_signature(order):
    """Who ordered what (quantities added up per product). Used to match a paid order to its pending one."""
    totals = {}
    for item in order["items"]:
        totals[item["product_id"]] = totals.get(item["product_id"], 0) + item["quantity"]
    return normalize_name(order["customer"]), tuple(sorted(totals.items()))


def process_one(order, products, processed_ids, options):
    """Process a single order using (and updating) processed_ids. Products are already checked."""
    apply_discount = options.get("apply_discount", True)
    include_shipping = options.get("include_shipping", True)

    # 1. Duplicate check first, so a repeated order always says "Duplicate".
    #    The one exception: a pending order may be paid later (exactly once).
    previous = None
    if isinstance(order, dict) and isinstance(order.get("order_id"), str):
        previous = processed_ids.get(normalize_id(order["order_id"]))
        if previous is not None:
            can_be_paid_now = previous["status"] == "pending" and order.get("payment_status") == "paid"
            if not can_be_paid_now:
                return make_result(order, "rejected", f"Duplicate order ID: {order['order_id'].strip()}")

    # 2. Normal validation.
    is_valid, message = validate_order(order, products)
    if not is_valid:
        return make_result(order, "rejected", message)

    # 3. A paid order that reuses a pending ID must be the same order.
    signature = order_signature(order)
    if previous is not None and previous["signature"] != signature:
        return make_result(order, "rejected",
                           f"Order {order['order_id'].strip()} does not match the pending order with the same ID")

    # 4. Price it.
    subtotal = calculate_order_subtotal(order, products)
    discount = calculate_discount(subtotal) if apply_discount else to_money(0)
    shipping = calculate_shipping(subtotal) if include_shipping else to_money(0)
    total = add_amounts(subtotal, -discount, shipping)

    # Copy the items so later changes to the result don't change the input order.
    items = [dict(item) for item in order["items"]]
    key = normalize_id(order["order_id"])

    if order["payment_status"] == "pending":
        processed_ids[key] = {"status": "pending", "signature": signature}
        return make_result(order, "pending", "Payment is pending",
                           subtotal, discount, shipping, total, items)

    # Stock is reduced only for paid orders that passed validation.
    for item in items:
        products[item["product_id"]]["stock"] -= item["quantity"]
    processed_ids[key] = {"status": "completed", "signature": signature}

    return make_result(order, "completed", "Order processed successfully",
                       subtotal, discount, shipping, total, items)


def check_processed_ids(processed_ids):
    """processed_ids must be a dict (or None). Returns the dict to use."""
    if processed_ids is None:
        return {}
    if not isinstance(processed_ids, dict):
        raise TypeError("processed_ids must be a dictionary (or None)")
    return processed_ids


def process_order(order, products, processed_ids=None, **options):
    """Validate, price and (if paid) deduct stock for one order.

    Pass the same `processed_ids` dictionary to every call to stop an order being
    processed twice. Without it, each call is independent (no duplicate protection).

    Options: apply_discount=True, include_shipping=True
    """
    check_options(options)
    processed_ids = check_processed_ids(processed_ids)
    validate_products(products)
    return process_one(order, products, processed_ids, options)


def process_all_orders(orders, products, processed_ids=None, **options):
    """Process a list of orders.

    A repeated order_id is rejected (IDs ignore spaces and capitals) so stock is never
    deducted twice. A pending order can be completed once by a later paid order with the
    same ID, customer and items. Pass `processed_ids` to keep this protection across calls.
    """
    check_options(options)
    if not isinstance(orders, list):
        raise TypeError("orders must be a list")
    processed_ids = check_processed_ids(processed_ids)
    validate_products(products)

    return [process_one(order, products, processed_ids, options) for order in orders]


def cancel_order(order_id, products, processed_ids, processed_orders=None):
    """Cancel a pending or completed order. A completed order's stock is returned.

    `processed_ids` must be the same dictionary used when the order was processed.
    If you also pass the list of processed order records, the matching records are
    marked "cancelled" so reports no longer count them. A cancelled ID cannot be reused.
    Returns a small record: {"order_id", "status", "reason"}.
    """
    if not isinstance(order_id, str) or not order_id.strip():
        return {"order_id": order_id, "status": "rejected", "reason": "Missing or invalid order_id"}
    if not isinstance(processed_ids, dict):
        raise TypeError("processed_ids must be a dictionary")
    validate_products(products)

    clean_id = order_id.strip()
    key = normalize_id(order_id)
    entry = processed_ids.get(key)
    if entry is None:
        return {"order_id": clean_id, "status": "rejected", "reason": f"Unknown order ID: {clean_id}"}
    if entry["status"] == "cancelled":
        return {"order_id": clean_id, "status": "rejected", "reason": f"Order {clean_id} is already cancelled"}

    returned_stock = entry["status"] == "completed"
    if returned_stock:
        quantities = entry["signature"][1]
        missing = [product_id for product_id, _ in quantities if product_id not in products]
        if missing:  # check first so stock is never returned halfway
            raise ValueError(f"Cannot return stock, unknown product(s): {', '.join(missing)}")
        for product_id, quantity in quantities:
            products[product_id]["stock"] += quantity

    entry["status"] = "cancelled"

    if processed_orders is not None:
        for record in processed_orders:
            if (isinstance(record, dict) and isinstance(record.get("order_id"), str)
                    and normalize_id(record["order_id"]) == key
                    and record.get("status") in ("completed", "pending")):
                record["status"] = "cancelled"
                record["reason"] = "Order cancelled"

    reason = "Order cancelled and stock returned" if returned_stock else "Order cancelled"
    return {"order_id": clean_id, "status": "cancelled", "reason": reason}


# ---------------------------------------------------------------- LEGB demo
STORE_NAME = "Demo Store"  # Global scope (read only, never modified)


def demonstrate_legb():
    """Return one value from each scope: Local, Enclosing, Global, Built-in."""
    enclosing_value = "defined in the outer function"

    def inner():
        local_value = "defined inside inner()"
        return {
            "Local": local_value,
            "Enclosing": enclosing_value,
            "Global": STORE_NAME,
            "Built-in": len("LEGB"),  # len() is found in the built-in scope
        }

    return inner()
