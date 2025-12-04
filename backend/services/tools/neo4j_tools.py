# backend/services/tools/neo4j_tools.py
"""
LangChain tools for querying the Fessi waste disposal knowledge graph.
These tools allow the agent to search for waste disposal information in Neo4j.
"""

from langchain_core.tools import tool
from backend.database.neo4j_db import neo4j_db


@tool
def search_waste_disposal(waste_item: str) -> dict:
    """Search for how to dispose of a specific waste item.

    Args:
        waste_item: The waste item to search for (e.g., 'plastic bottles', 'old TV', 'batteries')

    Returns:
        Disposal information including methods and locations
    """
    query = """
    MATCH (item:WasteItem)
    WHERE toLower(item.name) CONTAINS toLower($search)
       OR toLower(item.name_de) CONTAINS toLower($search)
       OR ANY(ex IN item.examples WHERE toLower(ex) CONTAINS toLower($search))
    MATCH (item)-[r:DISPOSED_VIA]->(method:DisposalMethod)
    OPTIONAL MATCH (method)-[:AVAILABLE_AT]->(loc:Location)
    OPTIONAL MATCH (item)-[:HAS_FAQ]->(faq:FAQ)
    RETURN item.name as item_name,
           item.name_de as item_name_de,
           collect(DISTINCT {
             method: method.name,
             method_de: method.name_de,
             type: method.type,
             color: method.color,
             frequency: method.frequency,
             instructions: method.instructions,
             priority: r.priority
           }) as disposal_methods,
           collect(DISTINCT {
             name: loc.name,
             address: loc.address,
             hours: loc.hours,
             phone: loc.phone
           }) as locations,
           collect(DISTINCT {
             question: faq.question_de,
             answer: faq.answer_de
           }) as faqs
    ORDER BY item.name
    LIMIT 5
    """
    try:
        results = neo4j_db.query(query, {"search": waste_item})
        # Filter out empty location/faq entries
        for result in results:
            result["locations"] = [loc for loc in result.get("locations", []) if loc.get("name")]
            result["faqs"] = [faq for faq in result.get("faqs", []) if faq.get("question")]
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


@tool
def get_disposal_method_details(method_name: str) -> dict:
    """Get detailed information about a specific disposal method.

    Args:
        method_name: Name of the disposal method (e.g., 'Yellow Bag', 'Wertstoffhof', 'Biotonne')

    Returns:
        Detailed information about the disposal method
    """
    query = """
    MATCH (method:DisposalMethod)
    WHERE toLower(method.name) CONTAINS toLower($search)
       OR toLower(method.name_de) CONTAINS toLower($search)
    OPTIONAL MATCH (method)-[:AVAILABLE_AT]->(loc:Location)
    OPTIONAL MATCH (item:WasteItem)-[:DISPOSED_VIA]->(method)
    RETURN method.name as name,
           method.name_de as name_de,
           method.type as type,
           method.color as color,
           method.frequency as frequency,
           method.instructions as instructions,
           collect(DISTINCT {name: loc.name, address: loc.address, hours: loc.hours, phone: loc.phone}) as locations,
           collect(DISTINCT item.name_de) as accepted_items
    LIMIT 1
    """
    try:
        results = neo4j_db.query(query, {"search": method_name})
        if results:
            # Filter out empty location entries
            results[0]["locations"] = [loc for loc in results[0].get("locations", []) if loc.get("name")]
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


@tool
def find_nearby_recycling_centers(city: str = "Frankfurt") -> dict:
    """Find recycling centers (Wertstoffhöfe) in a city.

    Args:
        city: City name to search in (default: Frankfurt)

    Returns:
        List of recycling centers with addresses and hours
    """
    query = """
    MATCH (loc:Location)
    WHERE toLower(loc.city) CONTAINS toLower($city)
    RETURN loc.name as name,
           loc.address as address,
           loc.postal_code as postal_code,
           loc.city as city,
           loc.hours as hours,
           loc.phone as phone,
           loc.lat as latitude,
           loc.lng as longitude
    ORDER BY loc.name
    """
    try:
        results = neo4j_db.query(query, {"city": city})
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


@tool
def get_waste_category_info(category: str) -> dict:
    """Get information about a waste category and all items in it.

    Args:
        category: Category name (e.g., 'Recycling', 'Hazardous', 'Electronic', 'Organic')

    Returns:
        Category information with all waste items and disposal methods
    """
    query = """
    MATCH (cat:WasteCategory)
    WHERE toLower(cat.name) CONTAINS toLower($search)
       OR toLower(cat.name_de) CONTAINS toLower($search)
    OPTIONAL MATCH (item:WasteItem)-[:BELONGS_TO]->(cat)
    OPTIONAL MATCH (item)-[:DISPOSED_VIA]->(method:DisposalMethod)
    OPTIONAL MATCH (cat)-[:HAS_FAQ]->(faq:FAQ)
    WITH cat, item, collect(DISTINCT method.name_de) as methods, faq
    RETURN cat.name as category_name,
           cat.name_de as category_name_de,
           cat.description as description,
           collect(DISTINCT {
             item: item.name_de,
             examples: item.examples,
             methods: methods
           }) as items,
           collect(DISTINCT {
             question: faq.question_de,
             answer: faq.answer_de
           }) as faqs
    LIMIT 1
    """
    try:
        results = neo4j_db.query(query, {"search": category})
        if results:
            # Filter out empty item and faq entries
            results[0]["items"] = [item for item in results[0].get("items", []) if item.get("item")]
            results[0]["faqs"] = [faq for faq in results[0].get("faqs", []) if faq.get("question")]
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


@tool
def answer_waste_faq(question_topic: str) -> dict:
    """Search FAQs about waste disposal.

    Args:
        question_topic: Topic to search for in FAQs

    Returns:
        Matching FAQ entries
    """
    query = """
    MATCH (faq:FAQ)
    WHERE toLower(faq.question) CONTAINS toLower($search)
       OR toLower(faq.question_de) CONTAINS toLower($search)
       OR toLower(faq.answer) CONTAINS toLower($search)
       OR toLower(faq.answer_de) CONTAINS toLower($search)
    RETURN faq.question_de as question,
           faq.answer_de as answer
    LIMIT 5
    """
    try:
        results = neo4j_db.query(query, {"search": question_topic})
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


def get_all_tools() -> list:
    """Return all available Neo4j tools for the agent."""
    return [
        search_waste_disposal,
        get_disposal_method_details,
        find_nearby_recycling_centers,
        get_waste_category_info,
        answer_waste_faq
    ]
