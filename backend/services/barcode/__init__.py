# backend/services/barcode/__init__.py
"""
Barcode product lookup via external APIs.
Copied from Graph-ETL-Pipeline/src/barcode/ for use as a chatbot agent tool.
"""

from .models import PackagingComponentInfo, ProductInfo
from .resolver import BarcodeResolver

__all__ = ["BarcodeResolver", "ProductInfo", "PackagingComponentInfo"]
