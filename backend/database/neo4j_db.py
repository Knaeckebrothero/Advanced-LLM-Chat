"""
Neo4j Knowledge Graph Database Manager.

This module provides a Neo4jDatabase class for managing Neo4j connections and
performing queries on the Fessi waste disposal knowledge graph. It provides
both synchronous and asynchronous access patterns.

Example usage:
    from backend.database import neo4j_db

    # Search for waste disposal info
    results = neo4j_db.search_waste_item("batteries")

    # Get recycling centers
    locations = neo4j_db.get_recycling_centers("Frankfurt")

    # Check connection status
    if neo4j_db.is_connected():
        stats = neo4j_db.get_stats()
"""
import logging
from contextlib import contextmanager
from typing import Optional, Generator

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from backend.config import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)

log = logging.getLogger(__name__)


class Neo4jDatabase:
    """
    Neo4j knowledge graph database manager.

    This class provides a clean interface for querying the waste disposal
    knowledge graph. It supports both synchronous and asynchronous queries
    with lazy driver initialization for efficiency.

    Attributes:
        uri: Neo4j connection URI.
        user: Neo4j username.
        password: Neo4j password.
        _driver: Synchronous Neo4j driver (lazy initialized).
        _async_driver: Asynchronous Neo4j driver (lazy initialized).

    Example:
        db = Neo4jDatabase()
        results = db.search_waste_item("plastic bottles")
    """

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
    ):
        """
        Initialize the Neo4j database manager.

        Args:
            uri: Neo4j connection URI (default from config).
            user: Neo4j username (default from config).
            password: Neo4j password (default from config).
        """
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self._driver = None
        self._async_driver = None

        log.debug(f"Neo4j database manager initialized for {self.uri}")

    @property
    def driver(self):
        """
        Get the synchronous Neo4j driver (lazy initialization).

        Returns:
            Neo4j Driver instance.

        Raises:
            ServiceUnavailable: If Neo4j is not reachable.
            AuthError: If authentication fails.
        """
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password)
                )
                self._driver.verify_connectivity()
                log.info(f"Connected to Neo4j at {self.uri}")
            except ServiceUnavailable as e:
                log.error(f"Neo4j service unavailable at {self.uri}: {e}")
                raise
            except AuthError as e:
                log.error(f"Neo4j authentication failed: {e}")
                raise
        return self._driver

    async def get_async_driver(self):
        """
        Get the asynchronous Neo4j driver (lazy initialization).

        Returns:
            AsyncNeo4j Driver instance.
        """
        if self._async_driver is None:
            try:
                self._async_driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password)
                )
                log.info(f"Async Neo4j driver initialized for {self.uri}")
            except Exception as e:
                log.error(f"Failed to initialize async Neo4j driver: {e}")
                raise
        return self._async_driver

    @contextmanager
    def session(self) -> Generator:
        """
        Context manager for Neo4j sessions.

        Yields a session that is automatically closed when the context exits.

        Yields:
            Neo4j Session object.

        Example:
            with neo4j_db.session() as session:
                result = session.run("MATCH (n) RETURN n LIMIT 10")
        """
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()

    def close(self) -> None:
        """
        Close all connections.

        Should be called when shutting down the application.
        """
        if self._driver:
            self._driver.close()
            self._driver = None
            log.info("Neo4j sync driver closed")

    async def aclose(self) -> None:
        """
        Close async connections.
        """
        if self._async_driver:
            await self._async_driver.close()
            self._async_driver = None
            log.info("Neo4j async driver closed")

    # =========================================================================
    # Core Query Methods
    # =========================================================================

    def query(self, cypher: str, params: dict = None) -> list:
        """
        Execute a Cypher query synchronously.

        Args:
            cypher: The Cypher query string.
            params: Optional dictionary of query parameters.

        Returns:
            List of dictionaries representing the query results.
        """
        with self.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    async def aquery(self, cypher: str, params: dict = None) -> list:
        """
        Execute a Cypher query asynchronously.

        Args:
            cypher: The Cypher query string.
            params: Optional dictionary of query parameters.

        Returns:
            List of dictionaries representing the query results.
        """
        driver = await self.get_async_driver()
        async with driver.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return records

    # =========================================================================
    # Connection Status
    # =========================================================================

    def is_connected(self) -> bool:
        """
        Check if Neo4j is available and connected.

        Returns:
            True if connected, False otherwise.
        """
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def get_stats(self) -> dict:
        """
        Get basic statistics about the knowledge graph.

        Returns:
            Dictionary with connection status and node counts.
        """
        try:
            result = self.query("""
                MATCH (n)
                RETURN labels(n) as label, count(n) as count
            """)
            node_counts = {}
            for r in result:
                if r["label"]:
                    for label in r["label"]:
                        node_counts[label] = node_counts.get(label, 0) + r["count"]

            # Get relationship count
            rel_result = self.query("MATCH ()-[r]->() RETURN count(r) as count")
            rel_count = rel_result[0]["count"] if rel_result else 0

            return {
                "connected": True,
                "node_counts": node_counts,
                "relationship_count": rel_count
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }

    # =========================================================================
    # Knowledge Graph Query Methods
    # =========================================================================

    def search_waste_item(self, search_term: str, limit: int = 5) -> list[dict]:
        """
        Search for waste disposal information by item name.

        Args:
            search_term: The waste item to search for.
            limit: Maximum number of results.

        Returns:
            List of matching items with disposal methods and locations.
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
        LIMIT $limit
        """
        try:
            results = self.query(query, {"search": search_term, "limit": limit})
            # Filter out empty location/faq entries
            for result in results:
                result["locations"] = [loc for loc in result.get("locations", []) if loc.get("name")]
                result["faqs"] = [faq for faq in result.get("faqs", []) if faq.get("question")]
            return results
        except Exception as e:
            log.error(f"Error searching waste item: {e}")
            return []

    def get_disposal_method(self, method_name: str) -> Optional[dict]:
        """
        Get detailed information about a disposal method.

        Args:
            method_name: Name of the disposal method.

        Returns:
            Disposal method details or None if not found.
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
            results = self.query(query, {"search": method_name})
            if results:
                result = results[0]
                result["locations"] = [loc for loc in result.get("locations", []) if loc.get("name")]
                return result
            return None
        except Exception as e:
            log.error(f"Error getting disposal method: {e}")
            return None

    def get_recycling_centers(self, city: str = "Frankfurt") -> list[dict]:
        """
        Find recycling centers in a city.

        Args:
            city: City name to search in.

        Returns:
            List of recycling center details.
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
            return self.query(query, {"city": city})
        except Exception as e:
            log.error(f"Error getting recycling centers: {e}")
            return []

    def get_waste_category(self, category_name: str) -> Optional[dict]:
        """
        Get information about a waste category.

        Args:
            category_name: Category name to search for.

        Returns:
            Category details with items and FAQs or None if not found.
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
            results = self.query(query, {"search": category_name})
            if results:
                result = results[0]
                result["items"] = [item for item in result.get("items", []) if item.get("item")]
                result["faqs"] = [faq for faq in result.get("faqs", []) if faq.get("question")]
                return result
            return None
        except Exception as e:
            log.error(f"Error getting waste category: {e}")
            return None

    def search_faqs(self, topic: str, limit: int = 5) -> list[dict]:
        """
        Search FAQs about waste disposal.

        Args:
            topic: Topic to search for.
            limit: Maximum number of results.

        Returns:
            List of matching FAQ entries.
        """
        query = """
        MATCH (faq:FAQ)
        WHERE toLower(faq.question) CONTAINS toLower($search)
           OR toLower(faq.question_de) CONTAINS toLower($search)
           OR toLower(faq.answer) CONTAINS toLower($search)
           OR toLower(faq.answer_de) CONTAINS toLower($search)
        RETURN faq.question_de as question,
               faq.answer_de as answer
        LIMIT $limit
        """
        try:
            return self.query(query, {"search": topic, "limit": limit})
        except Exception as e:
            log.error(f"Error searching FAQs: {e}")
            return []

    def get_all_categories(self) -> list[dict]:
        """
        Get all waste categories.

        Returns:
            List of all categories with basic info.
        """
        query = """
        MATCH (cat:WasteCategory)
        OPTIONAL MATCH (item:WasteItem)-[:BELONGS_TO]->(cat)
        RETURN cat.name as name,
               cat.name_de as name_de,
               cat.description as description,
               count(item) as item_count
        ORDER BY cat.name
        """
        try:
            return self.query(query)
        except Exception as e:
            log.error(f"Error getting categories: {e}")
            return []

    def get_all_disposal_methods(self) -> list[dict]:
        """
        Get all disposal methods.

        Returns:
            List of all disposal methods with basic info.
        """
        query = """
        MATCH (method:DisposalMethod)
        OPTIONAL MATCH (item:WasteItem)-[:DISPOSED_VIA]->(method)
        RETURN method.name as name,
               method.name_de as name_de,
               method.type as type,
               method.color as color,
               method.frequency as frequency,
               count(item) as item_count
        ORDER BY method.name
        """
        try:
            return self.query(query)
        except Exception as e:
            log.error(f"Error getting disposal methods: {e}")
            return []


# Singleton instance
neo4j_db = Neo4jDatabase()