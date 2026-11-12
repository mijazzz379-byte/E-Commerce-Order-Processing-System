"""Saving and loading data (JSON and CSV files). Standard library only."""

import csv
import json
import os
from decimal import Decimal

from order_processing import validate_products


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot save {type(value).__name__} to JSON")


def _write_text_atomically(path, text):
    """Write to a temporary file first so a crash can't leave a half-written file."""
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="") as file:
        file.write(text)
    os.replace(temp_path, path)


def _check_processed_ids(processed_ids):
    """Raise ValueError unless the saved ID records have the expected shape."""
    if not isinstance(processed_ids, dict):
        raise ValueError("processed_ids must be an object")
    clean = {}
    for key, entry in processed_ids.items():
        try:
            status = entry["status"]
            customer, quantities = entry["signature"]
            quantities = tuple((str(pid), int(qty)) for pid, qty in quantities)
            if status not in ("pending", "completed", "cancelled") or not isinstance(customer, str):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Saved record for order '{key}' is damaged") from None
        clean[str(key)] = {"status": status, "signature": (customer, quantities)}
    return clean


def save_state(path, products, processed_ids):
    """Save the inventory and the processed order IDs (so duplicates stay blocked next run)."""
    validate_products(products)
    data = {"products": products, "processed_ids": processed_ids}
    _write_text_atomically(path, json.dumps(data, indent=2, default=_json_default))


def load_state(path):
    """Load (products, processed_ids). Raises ValueError for damaged or invalid files."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from None
    if not isinstance(data, dict) or "products" not in data or "processed_ids" not in data:
        raise ValueError(f"{path} is not a saved state file")
    validate_products(data["products"])
    return data["products"], _check_processed_ids(data["processed_ids"])


def load_json_file(path, expected_type, label):
    """Read a JSON file that must hold a list (orders) or a dict (products)."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from None
    if not isinstance(data, expected_type):
        raise ValueError(f"{path} must contain {label}")
    return data


def load_orders(path):
    """Load a list of orders from a JSON file."""
    return load_json_file(path, list, "a list of orders")


def load_products(path):
    """Load and validate a products dictionary from a JSON file."""
    products = load_json_file(path, dict, "an object of products")
    validate_products(products)
    return products


def export_results_csv(path, processed_orders):
    """Write one row per processed order to a CSV file."""
    columns = ["order_id", "customer", "status", "reason", "subtotal", "discount", "shipping", "total"]
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for order in processed_orders:
            writer.writerow({column: order.get(column, "") for column in columns})
