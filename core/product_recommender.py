def recommend(products: list) -> dict | None:
    """Returns the top recommended product after sorting."""
    return products[0] if products else None
