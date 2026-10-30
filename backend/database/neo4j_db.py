"""
Neo4j Knowledge Graph Database Manager.

This module provides a Neo4jDatabase class for managing Neo4j connections and
running queries on the optional knowledge graph. It provides both synchronous
and asynchronous access patterns.

Example usage:
    from backend.database import neo4j_db

    # Run a read-only query
    results = neo4j_db.query_read("MATCH (n) RETURN labels(n) AS labels LIMIT 5")

    # Check connection status
    if neo4j_db.is_connected():
        stats = neo4j_db.get_stats()
"""
import logging
from contextlib import contextmanager
from typing import Generator

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

    This class provides a clean interface for querying the knowledge graph. It supports both synchronous and asynchronous queries
    with lazy driver initialization for efficiency.

    Attributes:
        uri: Neo4j connection URI.
        user: Neo4j username.
        password: Neo4j password.
        _driver: Synchronous Neo4j driver (lazy initialized).
        _async_driver: Asynchronous Neo4j driver (lazy initialized).

    Example:
        db = Neo4jDatabase()
        results = db.query_read("MATCH (n) RETURN count(n) AS nodes")
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
        log.debug(f"Executing Cypher query with params: {list((params or {}).keys())}")
        with self.session() as session:
            result = session.run(cypher, params or {})
            results = [dict(record) for record in result]
            log.debug(f"Query returned {len(results)} results")
            return results

    async def aquery(self, cypher: str, params: dict = None) -> list:
        """
        Execute a Cypher query asynchronously.

        Args:
            cypher: The Cypher query string.
            params: Optional dictionary of query parameters.

        Returns:
            List of dictionaries representing the query results.
        """
        log.debug(f"Executing async Cypher query with params: {list((params or {}).keys())}")
        driver = await self.get_async_driver()
        async with driver.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            log.debug(f"Async query returned {len(records)} results")
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
            log.debug("Neo4j connectivity verified")
            return True
        except Exception as e:
            log.debug(f"Neo4j connectivity check failed: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get basic statistics about the knowledge graph.

        Returns:
            Dictionary with connection status and node counts.
        """
        log.debug("Getting knowledge graph statistics")
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

            log.info(f"Knowledge graph stats: {sum(node_counts.values())} nodes, {rel_count} relationships")
            return {
                "connected": True,
                "node_counts": node_counts,
                "relationship_count": rel_count
            }
        except Exception as e:
            log.warning(f"Failed to get knowledge graph stats: {e}")
            return {
                "connected": False,
                "error": str(e)
            }

    # =========================================================================
    # Read-Only Queries
    # =========================================================================

    def query_read(self, cypher: str, params: dict = None, limit: int = None) -> list:
        """
        Execute a Cypher query inside a read transaction.

        Neo4j rejects writes (CREATE, MERGE, SET, DELETE, ...) in a read
        transaction, which makes this safe for queries written by the agent.

        Args:
            cypher: The Cypher query string.
            params: Optional dictionary of query parameters.
            limit: Optional maximum number of records to return.

        Returns:
            List of dictionaries; nodes and relationships are converted to dicts.
        """
        def read_records(tx) -> list:
            records = []
            for record in tx.run(cypher, params or {}):
                records.append(record.data())
                if limit is not None and len(records) >= limit:
                    break
            return records

        log.debug(f"Executing read-only Cypher query with params: {list((params or {}).keys())}")
        with self.session() as session:
            results = session.execute_read(read_records)
            log.debug(f"Read query returned {len(results)} results")
            return results


# Singleton instance
neo4j_db = Neo4jDatabase()