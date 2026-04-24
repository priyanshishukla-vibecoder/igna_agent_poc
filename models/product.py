from typing import Optional

from pydantic import BaseModel

# models/product.py defines the Product data model that the API uses to represent each scraped item in a clean, consistent structure. After products are collected from eBay, Best Buy, and Amazon, their details like name, price, site, condition, shipping, and URL are shaped into this model before being returned in the API response. This helps keep the output predictable, validated, and easy for both the backend and frontend to work with.

class Product(BaseModel):  #Pydantic model 

    """A single product scraped from an eCommerce site."""

    site: str
    name: str
    price: Optional[float] = None
    rating: Optional[float] = None
    condition: Optional[str] = None
    specs: Optional[str] = None
    shipping: Optional[str] = None
    url: Optional[str] = None
