# backend/services/cache/description_cache.py
"""
Cache for vision-generated file descriptions.

Stores descriptions in the database to avoid repeated API calls
for the same file + query combination.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded singleton
_description_cache: Optional["DescriptionCache"] = None


def get_description_cache() -> "DescriptionCache":
    """Get or create the DescriptionCache singleton instance."""
    global _description_cache
    if _description_cache is None:
        from backend.database import db
        _description_cache = DescriptionCache(db)
    return _description_cache


class DescriptionCache:
    """
    Cache for generated image/document descriptions.

    Caches vision model outputs to avoid repeated API calls for the
    same file. Cache keys are SHA256 hashes of file_id + query.
    """

    def __init__(self, db):
        """
        Initialize the description cache.

        Args:
            db: Database instance for storing cache entries.
        """
        self.db = db

    def _make_key(self, file_id: str, query: Optional[str] = None) -> str:
        """
        Generate cache key from file ID and optional query.

        Args:
            file_id: The file identifier.
            query: Optional query used for description.

        Returns:
            SHA256 hash of the combined key data.
        """
        key_data = {"file_id": file_id, "query": query or ""}
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()

    async def get(self, file_id: str, query: Optional[str] = None) -> Optional[str]:
        """
        Retrieve cached description.

        Args:
            file_id: The file identifier.
            query: Optional query used for description.

        Returns:
            Cached description or None if not found.
        """
        cache_key = self._make_key(file_id, query)
        try:
            result = self.db.get_cache_entry(cache_key)
            if result:
                logger.debug(f"Cache hit for file_id={file_id}, query={query}")
            return result
        except Exception as e:
            logger.warning(f"Cache read error for {cache_key}: {e}")
            return None

    async def set(
        self,
        file_id: str,
        description: str,
        query: Optional[str] = None
    ) -> None:
        """
        Store description in cache.

        Args:
            file_id: The file identifier.
            description: The generated description.
            query: Optional query used for description.
        """
        cache_key = self._make_key(file_id, query)
        try:
            self.db.set_cache_entry(
                cache_key=cache_key,
                file_id=file_id,
                description=description,
                query=query
            )
            logger.debug(f"Cached description for file_id={file_id}, query={query}")
        except Exception as e:
            logger.warning(f"Cache write error for {cache_key}: {e}")
            # Non-fatal: continue without caching

    async def delete_by_file(self, file_id: str) -> int:
        """
        Delete all cached descriptions for a file.

        Called when a file is deleted to clean up stale cache entries.

        Args:
            file_id: The file identifier.

        Returns:
            Number of entries deleted.
        """
        try:
            count = self.db.delete_cache_by_file(file_id)
            if count > 0:
                logger.info(f"Deleted {count} cache entries for file_id={file_id}")
            return count
        except Exception as e:
            logger.warning(f"Cache delete error for file_id={file_id}: {e}")
            return 0
