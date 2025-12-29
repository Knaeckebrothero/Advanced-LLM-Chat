# backend/services/tools/web_search_tools.py
"""
Web search tools for the Fessi agent using Tavily.
Allows the agent to search the web for current information.
"""

import logging
import os
from langchain_community.tools.tavily_search import TavilySearchResults

log = logging.getLogger(__name__)

# Tavily API key from environment
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def get_web_search_tool():
    """
    Get the Tavily web search tool if configured.

    Returns:
        TavilySearchResults tool or None if not configured.
    """
    if not TAVILY_API_KEY:
        log.warning("TAVILY_API_KEY not set - web search tool disabled")
        return None

    try:
        tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
            include_images=False,
        )
        log.info("Tavily web search tool initialized")
        return tool
    except Exception as e:
        log.error(f"Failed to initialize Tavily web search tool: {e}")
        return None