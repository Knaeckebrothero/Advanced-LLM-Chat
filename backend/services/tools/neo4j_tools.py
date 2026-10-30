# backend/services/tools/neo4j_tools.py
"""
Tools for reading the optional Neo4j knowledge graph.

The tools make no assumptions about the graph's schema: the agent inspects the
schema first, then searches for nodes or runs read-only Cypher queries.
They are only registered when NEO4J_ENABLED is set (see backend/llm/tools.py,
which also holds the schemas the model sees). The functions are synchronous;
the agent loop runs them in a worker thread.
"""

import json
import logging
from backend.config import NEO4J_MAX_RESULTS

log = logging.getLogger(__name__)

# Long values (documents, embeddings) are shortened before they reach the model
MAX_STRING_LENGTH = 2000
MAX_LIST_LENGTH = 50


def _compact(value):
    """Make a query result JSON-safe and shorten long strings and lists."""
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_compact(item) for item in value[:MAX_LIST_LENGTH]]
        if len(value) > MAX_LIST_LENGTH:
            items.append(f"... ({len(value) - MAX_LIST_LENGTH} more items)")
        return items
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return value[:MAX_STRING_LENGTH] + "..."
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Neo4j temporal and spatial types
    return json.loads(json.dumps(value, default=str))


def _db():
    """The Neo4j database manager, imported on first use so the driver is only needed with the graph enabled."""
    from backend.database.neo4j_db import neo4j_db
    return neo4j_db


def _limited_read(cypher: str, params: dict = None) -> dict:
    """Run a read query and report whether the result was cut off."""
    rows = _db().query_read(cypher, params, limit=NEO4J_MAX_RESULTS + 1)
    return {
        "results": _compact(rows[:NEO4J_MAX_RESULTS]),
        "truncated": len(rows) > NEO4J_MAX_RESULTS
    }


def get_graph_schema() -> dict:
    """Get the structure of the knowledge graph.

    Call this before searching or querying the graph to learn which node labels,
    relationship types and properties exist.

    Returns:
        Node and relationship counts, the properties of each node label and the
        relationship patterns that connect them
    """
    try:
        log.debug("Getting knowledge graph schema")
        neo4j_db = _db()
        counts = neo4j_db.query_read("""
            CALL { MATCH (n) RETURN count(n) AS nodes }
            CALL { MATCH ()-[r]->() RETURN count(r) AS relationships }
            RETURN nodes, relationships
        """)
        node_types = neo4j_db.query_read("""
            CALL db.schema.nodeTypeProperties()
            YIELD nodeLabels, propertyName
            RETURN nodeLabels AS labels, collect(DISTINCT propertyName) AS properties
        """)
        patterns = neo4j_db.query_read("""
            MATCH (a)-[r]->(b)
            RETURN DISTINCT labels(a) AS from, type(r) AS relationship, labels(b) AS to
            LIMIT 100
        """)
        for node_type in node_types:
            node_type["properties"] = [name for name in node_type["properties"] if name]
        log.info(f"Graph schema: {len(node_types)} node types, {len(patterns)} relationship patterns")
        return {
            "counts": counts[0] if counts else {},
            "node_types": node_types,
            "relationship_patterns": patterns
        }
    except Exception as e:
        log.error(f"Error getting knowledge graph schema: {e}")
        return {"error": str(e)}


def search_graph(text: str) -> dict:
    """Search the knowledge graph for nodes whose text properties contain the given text.

    The search is case-insensitive and looks at every string property (and list of
    strings) of every node.

    Args:
        text: The text to search for (e.g., a name, keyword or phrase)

    Returns:
        Matching nodes with their id, labels and properties
    """
    query = """
    MATCH (n)
    WHERE any(key IN keys(n) WHERE
        (n[key] IS :: STRING AND toLower(n[key]) CONTAINS toLower($text))
        OR (n[key] IS :: LIST<STRING NOT NULL> AND any(item IN n[key] WHERE toLower(item) CONTAINS toLower($text))))
    RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties
    """
    try:
        log.debug(f"Searching knowledge graph for: '{text}'")
        result = _limited_read(query, {"text": text})
        log.info(f"Found {len(result['results'])} nodes matching '{text}'")
        return result
    except Exception as e:
        log.error(f"Error searching knowledge graph for '{text}': {e}")
        return {"error": str(e), "results": []}


def query_graph(cypher: str) -> dict:
    """Run a read-only Cypher query against the knowledge graph.

    Call get_graph_schema first so the query only uses labels, relationship types
    and properties that exist. Writes (CREATE, MERGE, SET, DELETE, ...) are rejected.
    Return only the fields you need, and only a limited number of rows comes back.

    Args:
        cypher: The Cypher query to run (e.g., 'MATCH (p:Person)-[:KNOWS]->(f) RETURN p.name, f.name')

    Returns:
        The query results, and whether they were truncated
    """
    try:
        log.debug(f"Running agent Cypher query: {cypher}")
        result = _limited_read(cypher)
        log.info(f"Agent Cypher query returned {len(result['results'])} rows")
        return result
    except Exception as e:
        log.error(f"Error running agent Cypher query: {e}")
        return {"error": str(e), "results": []}

