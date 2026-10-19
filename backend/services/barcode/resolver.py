"""Barcode resolver: look up product information by barcode number via APIs.

Lookup chain (stops at first hit):
  1. Open Food Facts — food products (~4M)
  2. Open Beauty Facts — cosmetics/personal care (~13K)
  3. UPCitemdb — all products, name+brand+category only (100 req/day free)

Copied from Graph-ETL-Pipeline/src/barcode/resolver.py with import path fix.
"""

import logging
from datetime import datetime, timezone

import requests

from .models import PackagingComponentInfo, ProductInfo

logger = logging.getLogger(__name__)

OFF_API_BASE = "https://world.openfoodfacts.org/api/v2/product"
OBF_API_BASE = "https://world.openbeautyfacts.org/api/v2/product"
UPCITEMDB_API_BASE = "https://api.upcitemdb.com/prod/trial/lookup"
OFF_USER_AGENT = "FessiWasteBot/1.0 (https://github.com/fessi-chatbot)"
OFF_TIMEOUT = 10  # seconds

# Request only the fields we need to reduce payload size
OFF_FIELDS = ",".join([
    "product_name",
    "product_name_de",
    "brands",
    "quantity",
    "categories",
    "categories_tags",
    "packaging",
    "packaging_tags",
    "packaging_materials_tags",
    "ecoscore_grade",
    "nutriscore_grade",
    "labels",
    "image_url",
    "image_front_url",
    "packagings",
])


class BarcodeResolver:
    """Resolve barcode numbers to product information via APIs.

    Usage:
        resolver = BarcodeResolver()
        product = resolver.lookup("3017620422003")
        if product.found:
            print(product.product_name)   # "Nutella"
            print(product.packaging_materials_tags)
    """

    def __init__(
        self,
        timeout: int = OFF_TIMEOUT,
        user_agent: str = OFF_USER_AGENT,
    ):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def lookup(self, barcode: str) -> ProductInfo:
        """Look up product information by barcode number.

        Tries Open Food Facts first. Returns ProductInfo with found=False
        if the barcode is not in any database.

        Args:
            barcode: Barcode number string (EAN-13, UPC-A, etc.)

        Returns:
            ProductInfo with product data (found=True) or empty (found=False).
        """
        barcode = barcode.strip()
        if not barcode:
            logger.warning("Empty barcode provided")
            return ProductInfo(barcode="", found=False)

        logger.info("Looking up barcode: %s", barcode)

        result = self._lookup_openfoodfacts(barcode)
        if result.found:
            return result

        result = self._lookup_openbeautyfacts(barcode)
        if result.found:
            return result

        result = self._lookup_upcitemdb(barcode)
        if result.found:
            return result

        logger.info("Barcode %s not found in any API", barcode)
        return ProductInfo(
            barcode=barcode,
            found=False,
            lookup_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _lookup_openfoodfacts(self, barcode: str) -> ProductInfo:
        """Query Open Food Facts API.

        API docs: https://openfoodfacts.github.io/openfoodfacts-server/api/
        Rate limit: ~100 requests/minute.
        """
        url = f"{OFF_API_BASE}/{barcode}"
        params = {"fields": OFF_FIELDS}

        try:
            response = self.session.get(
                url, params=params, timeout=self.timeout
            )
        except requests.Timeout:
            logger.warning(
                "Open Food Facts API timeout for barcode %s", barcode
            )
            return ProductInfo(barcode=barcode, found=False)
        except requests.RequestException as e:
            logger.warning(
                "Open Food Facts API error for barcode %s: %s", barcode, e
            )
            return ProductInfo(barcode=barcode, found=False)

        if response.status_code != 200:
            logger.debug(
                "Open Food Facts returned status %d", response.status_code
            )
            return ProductInfo(barcode=barcode, found=False)

        data = response.json()
        product = data.get("product")

        if not product:
            logger.debug(
                "No product data in Open Food Facts response for %s", barcode
            )
            return ProductInfo(barcode=barcode, found=False)

        timestamp = datetime.now(timezone.utc).isoformat()

        # Parse structured per-component packaging data
        packaging_components = []
        for comp in product.get("packagings") or []:
            packaging_components.append(
                PackagingComponentInfo(
                    material=comp.get("material") or "",
                    shape=comp.get("shape") or "",
                    recycling=comp.get("recycling") or "",
                    number_of_units=comp.get("number_of_units") or 1,
                    weight_measured=comp.get("weight_measured"),
                    food_contact=comp.get("food_contact"),
                )
            )

        return ProductInfo(
            barcode=barcode,
            found=True,
            source_api="openfoodfacts",
            product_name=product.get("product_name", ""),
            product_name_de=product.get("product_name_de", ""),
            brands=product.get("brands", ""),
            quantity=product.get("quantity", ""),
            categories=product.get("categories", ""),
            categories_tags=product.get("categories_tags") or [],
            packaging=product.get("packaging", ""),
            packaging_tags=product.get("packaging_tags") or [],
            packaging_materials_tags=product.get("packaging_materials_tags")
            or [],
            packaging_components=packaging_components,
            ecoscore_grade=product.get("ecoscore_grade", ""),
            nutriscore_grade=product.get("nutriscore_grade", ""),
            labels=product.get("labels", ""),
            image_url=product.get("image_url")
            or product.get("image_front_url", ""),
            lookup_timestamp=timestamp,
        )

    def _lookup_openbeautyfacts(self, barcode: str) -> ProductInfo:
        """Query Open Beauty Facts API (cosmetics, personal care).

        Same API schema as Open Food Facts, different base URL.
        Covers ~13K products: shampoos, soaps, cosmetics, etc.
        """
        url = f"{OBF_API_BASE}/{barcode}"
        params = {"fields": OFF_FIELDS}

        try:
            response = self.session.get(
                url, params=params, timeout=self.timeout
            )
        except requests.Timeout:
            logger.warning(
                "Open Beauty Facts API timeout for barcode %s", barcode
            )
            return ProductInfo(barcode=barcode, found=False)
        except requests.RequestException as e:
            logger.warning(
                "Open Beauty Facts API error for barcode %s: %s", barcode, e
            )
            return ProductInfo(barcode=barcode, found=False)

        if response.status_code != 200:
            logger.debug(
                "Open Beauty Facts returned status %d", response.status_code
            )
            return ProductInfo(barcode=barcode, found=False)

        data = response.json()
        product = data.get("product")

        if not product:
            logger.debug(
                "No product data in Open Beauty Facts response for %s", barcode
            )
            return ProductInfo(barcode=barcode, found=False)

        timestamp = datetime.now(timezone.utc).isoformat()

        packaging_components = []
        for comp in product.get("packagings") or []:
            packaging_components.append(
                PackagingComponentInfo(
                    material=comp.get("material") or "",
                    shape=comp.get("shape") or "",
                    recycling=comp.get("recycling") or "",
                    number_of_units=comp.get("number_of_units") or 1,
                    weight_measured=comp.get("weight_measured"),
                    food_contact=comp.get("food_contact"),
                )
            )

        return ProductInfo(
            barcode=barcode,
            found=True,
            source_api="openbeautyfacts",
            product_name=product.get("product_name", ""),
            product_name_de=product.get("product_name_de", ""),
            brands=product.get("brands", ""),
            quantity=product.get("quantity", ""),
            categories=product.get("categories", ""),
            categories_tags=product.get("categories_tags") or [],
            packaging=product.get("packaging", ""),
            packaging_tags=product.get("packaging_tags") or [],
            packaging_materials_tags=product.get("packaging_materials_tags")
            or [],
            packaging_components=packaging_components,
            ecoscore_grade=product.get("ecoscore_grade", ""),
            labels=product.get("labels", ""),
            image_url=product.get("image_url")
            or product.get("image_front_url", ""),
            lookup_timestamp=timestamp,
        )

    def _lookup_upcitemdb(self, barcode: str) -> ProductInfo:
        """Query UPCitemdb API (all product categories, name+brand+category).

        Free tier: 100 requests/day, no API key required.
        Returns minimal product info (no packaging or material data).
        API docs: https://www.upcitemdb.com/wp/docs/main/development/responses/
        """
        try:
            response = self.session.get(
                UPCITEMDB_API_BASE,
                params={"upc": barcode},
                timeout=self.timeout,
            )
        except requests.Timeout:
            logger.warning("UPCitemdb timeout for barcode %s", barcode)
            return ProductInfo(barcode=barcode, found=False)
        except requests.RequestException as e:
            logger.warning("UPCitemdb error for barcode %s: %s", barcode, e)
            return ProductInfo(barcode=barcode, found=False)

        if response.status_code == 429:
            logger.warning("UPCitemdb rate limit reached (100/day)")
            return ProductInfo(barcode=barcode, found=False)
        if response.status_code != 200:
            logger.debug("UPCitemdb returned status %d", response.status_code)
            return ProductInfo(barcode=barcode, found=False)

        data = response.json()
        items = data.get("items") or []
        if not items:
            logger.debug("No items in UPCitemdb response for %s", barcode)
            return ProductInfo(barcode=barcode, found=False)

        item = items[0]
        timestamp = datetime.now(timezone.utc).isoformat()

        # Map Google product taxonomy category to categories_tags
        category = item.get("category", "")
        categories_tags = (
            [f"upcitemdb:{category}"] if category else []
        )

        return ProductInfo(
            barcode=barcode,
            found=True,
            source_api="upcitemdb",
            product_name=item.get("title", ""),
            brands=item.get("brand", ""),
            categories=category,
            categories_tags=categories_tags,
            image_url=(item.get("images") or [""])[0],
            lookup_timestamp=timestamp,
        )

    def close(self):
        """Close the HTTP session."""
        self.session.close()
