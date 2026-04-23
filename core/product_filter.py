import re


def filter_products(products: list, criteria: dict) -> list:
    """
    Filters raw scraped products against structured criteria.
    Removes products that do not meet price, RAM, storage, or brand requirements.
    """
    filtered = []

    for product in products:
        if criteria.get("max_price") and product.get("price"):
            if product["price"] > criteria["max_price"]:
                continue

        if criteria.get("brand"):
            name_lower = (product.get("name") or "").lower()
            if criteria["brand"].lower() not in name_lower:
                continue

        if criteria.get("min_ram_gb"):
            combined = f"{product.get('name', '')} {product.get('specs', '')}".lower()
            ram_match = re.search(r"(\d+)\s*gb\s*(?:ram|memory)", combined)
            if ram_match and int(ram_match.group(1)) < criteria["min_ram_gb"]:
                continue

        if criteria.get("min_storage_gb"):
            combined = f"{product.get('name', '')} {product.get('specs', '')}".lower()
            storage_match = re.search(
                r"(\d+)\s*(?:gb|tb)\s*(?:ssd|storage|hdd|flash)",
                combined,
            )
            if storage_match and int(storage_match.group(1)) < criteria["min_storage_gb"]:
                continue

        if criteria.get("condition"):
            product_condition = (product.get("condition") or "").lower()
            if criteria["condition"] == "new" and "pre" in product_condition:
                continue
            if criteria["condition"] == "pre-owned" and product_condition == "new":
                continue

        filtered.append(product)

    filtered.sort(key=lambda item: (item.get("price") or 9999, -(item.get("rating") or 0)))
    return filtered
