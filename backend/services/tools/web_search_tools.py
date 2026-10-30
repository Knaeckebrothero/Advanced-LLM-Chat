# backend/services/tools/web_search_tools.py
"""
Web search tool for the chat agent using the Tavily API.
Allows the agent to search the web for current information.
It is only registered when TAVILY_API_KEY is set (see backend/llm/tools.py).
"""

import logging
from typing import Optional

from backend.config import TAVILY_API_KEY

log = logging.getLogger(__name__)

# Number of results and the length of each result's text that reach the model
MAX_RESULTS = 5
MAX_CONTENT_LENGTH = 2000

_client = None


def is_web_search_available() -> bool:
    """Whether web search is configured (TAVILY_API_KEY is set)."""
    return bool(TAVILY_API_KEY)


def _get_client():
    """The shared Tavily client, created on first use."""
    global _client
    if _client is None:
        from tavily import AsyncTavilyClient
        _client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        log.info("Tavily web search client initialized")
    return _client


async def web_search(query: str, max_results: Optional[int] = None) -> dict:
    """
    Search the web with Tavily.

    Args:
        query: The search query.
        max_results: Number of results (default and maximum: MAX_RESULTS).

    Returns:
        A short answer (when Tavily has one) and the top results with title, URL and content.
    """
    limit = min(max_results or MAX_RESULTS, MAX_RESULTS)
    log.debug(f"Searching the web for: '{query}' (max {limit} results)")
    response = await _get_client().search(
        query=query,
        max_results=limit,
        search_depth="advanced",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
    )
    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": (item.get("content") or "")[:MAX_CONTENT_LENGTH],
        }
        for item in response.get("results", [])
    ]
    log.info(f"Web search for '{query}' returned {len(results)} results")
    return {"answer": response.get("answer"), "results": results}
