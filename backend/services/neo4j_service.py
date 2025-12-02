# backend/services/neo4j_service.py
"""
Neo4j database connection service for the Fessi knowledge graph.
Provides both synchronous and asynchronous access to the Neo4j database.
"""

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
import os
import logging

logger = logging.getLogger(__name__)


class Neo4jService:
    """Service for managing Neo4j database connections."""

    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "fessi_neo4j_dev")
        self._driver = None
        self._async_driver = None

    def get_driver(self):
        """Get synchronous driver (lazy initialization)."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password)
                )
                # Verify connectivity
                self._driver.verify_connectivity()
                logger.info(f"Connected to Neo4j at {self.uri}")
            except ServiceUnavailable as e:
                logger.error(f"Neo4j service unavailable at {self.uri}: {e}")
                raise
            except AuthError as e:
                logger.error(f"Neo4j authentication failed: {e}")
                raise
        return self._driver

    async def get_async_driver(self):
        """Get async driver (lazy initialization)."""
        if self._async_driver is None:
            try:
                self._async_driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password)
                )
                logger.info(f"Async Neo4j driver initialized for {self.uri}")
            except Exception as e:
                logger.error(f"Failed to initialize async Neo4j driver: {e}")
                raise
        return self._async_driver

    def close(self):
        """Close all connections."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j sync driver closed")

    async def aclose(self):
        """Close async connections."""
        if self._async_driver:
            await self._async_driver.close()
            self._async_driver = None
            logger.info("Neo4j async driver closed")

    def query(self, cypher: str, params: dict = None) -> list:
        """Execute a Cypher query synchronously.

        Args:
            cypher: The Cypher query string
            params: Optional dictionary of query parameters

        Returns:
            List of dictionaries representing the query results
        """
        driver = self.get_driver()
        with driver.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    async def aquery(self, cypher: str, params: dict = None) -> list:
        """Execute a Cypher query asynchronously.

        Args:
            cypher: The Cypher query string
            params: Optional dictionary of query parameters

        Returns:
            List of dictionaries representing the query results
        """
        driver = await self.get_async_driver()
        async with driver.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return records

    def is_connected(self) -> bool:
        """Check if Neo4j is available and connected."""
        try:
            driver = self.get_driver()
            driver.verify_connectivity()
            return True
        except Exception:
            return False

    def get_stats(self) -> dict:
        """Get basic statistics about the knowledge graph."""
        try:
            result = self.query("""
                MATCH (n)
                RETURN labels(n) as label, count(n) as count
            """)
            return {
                "connected": True,
                "node_counts": {r["label"][0]: r["count"] for r in result if r["label"]}
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }


# Singleton instance
neo4j_service = Neo4jService()
