from typing import Optional

from pydantic import BaseModel


class Product(BaseModel):
    """A single product scraped from an eCommerce site."""

    site: str
    name: str
    price: Optional[float] = None
    rating: Optional[float] = None
    condition: Optional[str] = None
    specs: Optional[str] = None
    shipping: Optional[str] = None
    url: Optional[str] = None
