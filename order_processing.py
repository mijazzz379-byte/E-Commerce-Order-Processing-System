"""Order validation, pricing and processing logic (no classes, no globals needed)."""

from decimal import Decimal, ROUND_HALF_UP


# ---------------------------------------------------------------- money helpers
def to_money(value):
    """Convert a number to a Decimal rounded to 2 places (half-up)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    return {
        "order_id": order.get("order_id") if is_dict else None,
        "customer": order.get("customer") if is_dict else None,
        "status": status,
        "reason": reason,
        "subtotal": to_money(subtotal),
        "discount": to_money(discount),
        "shipping": to_money(shipping),
        "total": to_money(total),
        "items": items if items is not None else [],
    }


def process_order(order, products, **options):
    """Validate, price and (if paid) deduct stock for one order.

    Options: apply_discount=True, include_shipping=True
    """
    check_options(options)
    apply_discount = options.get("apply_discount", True)
    include_shipping = options.get("include_shipping", True)

    is_valid, message = validate_order(order, products)
    if not is_valid:
        return make_result(order, "rejected", message)

    subtotal = calculate_order_subtotal(order, products)
    discount = calculate_discount(subtotal) if apply_discount else to_money(0)
    shipping = calculate_shipping(subtotal) if include_shipping else to_money(0)
    total = add_amounts(subtotal, -discount, shipping)

    # Copy the items so later changes to the result don't change the input order.
    items = [dict(item) for item in order["items"]]

    if order["payment_status"] == "pending":
        return make_result(order, "pending", "Payment is pending",
                           subtotal, discount, shipping, total, items)

    # Stock is reduced only for paid orders that passed validation.
    for item in items:
        products[item["product_id"]]["stock"] -= item["quantity"]

    return make_result(order, "completed", "Order processed successfully",
                       subtotal, discount, shipping, total, items)


def process_all_orders(orders, products, **options):
    """Process a list of orders; a repeated order_id is rejected (no double stock deduction)."""
    check_options(options)
    seen_ids = set()
    results = []

    for order in orders:
        order_id = order.get("order_id") if isinstance(order, dict) else None
        if isinstance(order_id, str) and order_id in seen_ids:
            results.append(make_result(order, "rejected", f"Duplicate order ID: {order_id}"))
            continue

        result = process_order(order, products, **options)
        if result["status"] != "rejected":
            seen_ids.add(result["order_id"])
        results.append(result)

    return results


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
