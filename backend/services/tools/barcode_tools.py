# backend/services/tools/barcode_tools.py
"""
LangChain tool for product barcode lookup.
Checks Neo4j knowledge graph first, falls back to external APIs.
"""

import logging

from langchain_core.tools import tool

from backend.database.neo4j_db import neo4j_db

log = logging.getLogger(__name__)

# Lazy-initialized resolver (avoids creating HTTP session at import time)
_resolver = None


def _get_resolver():
    """Get or create the shared BarcodeResolver instance."""
    global _resolver
    if _resolver is None:
        from backend.services.barcode import BarcodeResolver
        _resolver = BarcodeResolver()
    return _resolver


@tool
def lookup_product_barcode(ean: str) -> dict:
    """Look up a product by its EAN/UPC barcode to determine how to dispose of it and its packaging.

    Use this tool when the user provides a barcode number (EAN-13, EAN-8, or UPC).
    Returns product information including name, brand, and packaging materials,
    along with disposal instructions for each packaging component.

    Args:
        ean: The barcode number (EAN-13, EAN-8, or UPC-A string, e.g., '3017620422003')

    Returns:
        Product information with packaging materials and disposal routes
    """
    ean = ean.strip()
    if not ean:
        return {"error": "Empty barcode provided", "found": False}

    log.info(f"Looking up product barcode: {ean}")

    # Step 1: Check Neo4j for existing Product node with waste stream routing
    graph_result = _lookup_in_graph(ean)
    if graph_result and graph_result.get("found"):
        log.info(f"Product {ean} found in knowledge graph")
        return graph_result

    # Step 2: Fall back to external API cascade
    log.info(f"Product {ean} not in graph, querying external APIs")
    api_result = _lookup_via_api(ean)
    return api_result


def _lookup_in_graph(ean: str) -> dict | None:
    """Query Neo4j for a Product node with packaging components and waste streams."""
    query = """
    MATCH (p:Product {ean: $ean})
    OPTIONAL MATCH (p)-[:HAS_COMPONENT]->(comp:PackagingComponent)-[:MADE_OF]->(mat:Material)
    OPTIONAL MATCH (mat)-[:DEFAULT_STREAM]->(ws:WasteStream)
    OPTIONAL MATCH (p)-[:IS_A]->(wi:WasteItem)
    OPTIONAL MATCH (wi)-[:DISPOSED_IN]->(wis:WasteStream)
    OPTIONAL MATCH (wi)-[:DISPOSED_AT]->(fac:Facility)
    RETURN p.name as product_name,
           p.name_de as product_name_de,
           p.brand as brand,
           p.ean as ean,
           p.quantity as quantity,
           p.image_url as image_url,
           collect(DISTINCT {
             shape: comp.shape,
             material: mat.name,
             material_de: mat.name_de,
             material_tag: mat.tag,
             stream: ws.name,
             stream_de: ws.name_de,
             recycling: comp.recycling,
             weight: comp.weight_measured
           }) as components,
           wi.name as waste_item_name,
           wi.name_de as waste_item_name_de,
           collect(DISTINCT wis.name) as waste_streams,
           collect(DISTINCT {
             name: fac.name,
             address: fac.address,
             hours: fac.hours
           }) as facilities
    LIMIT 1
    """
    try:
        results = neo4j_db.query(query, {"ean": ean})
        if not results or not results[0].get("product_name"):
            return None

        row = results[0]

        # Filter out empty component entries (from OPTIONAL MATCH)
        components = [
            c for c in row.get("components", [])
            if c.get("material") or c.get("shape")
        ]

        # Filter out empty facility entries
        facilities = [
            f for f in row.get("facilities", [])
            if f.get("name")
        ]

        # Filter out empty/None waste streams
        waste_streams = [ws for ws in row.get("waste_streams", []) if ws]

        return {
            "found": True,
            "source": "knowledge_graph",
            "product_name": row.get("product_name") or row.get("product_name_de", ""),
            "brand": row.get("brand", ""),
            "ean": row.get("ean", ean),
            "quantity": row.get("quantity", ""),
            "image_url": row.get("image_url", ""),
            "packaging_components": components,
            "waste_item": row.get("waste_item_name_de") or row.get("waste_item_name", ""),
            "waste_streams": waste_streams,
            "facilities": facilities,
        }

    except Exception as e:
        log.error(f"Error querying Neo4j for barcode {ean}: {e}")
        return None


def _lookup_via_api(ean: str) -> dict:
    """Look up product via external API cascade and format for agent consumption."""
    try:
        resolver = _get_resolver()
        product = resolver.lookup(ean)
    except Exception as e:
        log.error(f"Error looking up barcode {ean} via API: {e}")
        return {"error": f"API lookup failed: {str(e)}", "found": False}

    if not product.found:
        return {
            "found": False,
            "ean": ean,
            "message": "Product not found in any database. The barcode may be invalid or not yet catalogued.",
        }

    # Format packaging components for the agent
    components = []
    for comp in product.packaging_components:
        components.append({
            "material": comp.material,
            "shape": comp.shape,
            "recycling": comp.recycling,
            "weight": comp.weight_measured,
        })

    return {
        "found": True,
        "source": product.source_api,
        "product_name": product.product_name_de or product.product_name,
        "brand": product.brands,
        "ean": product.barcode,
        "quantity": product.quantity,
        "categories": product.categories,
        "image_url": product.image_url,
        "packaging_description": product.packaging,
        "packaging_materials_tags": product.packaging_materials_tags,
        "packaging_components": components,
        "ecoscore_grade": product.ecoscore_grade,
        "note": (
            "Product found via external API (not yet in knowledge graph). "
            "Use packaging_materials_tags and packaging_components to determine "
            "the correct waste stream for each part of the packaging."
        ),
    }


def get_barcode_tools() -> list:
    """Return all barcode-related tools for the agent."""
    return [lookup_product_barcode]
