# backend/services/cache/__init__.py
"""Cache services for the Fessi backend."""

from .description_cache import DescriptionCache, get_description_cache

__all__ = ['DescriptionCache', 'get_description_cache']
