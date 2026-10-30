"""
Database module for PostgreSQL operations.

This module exports the Database class and a module-level instance
for use throughout the application.

Example usage:
    from backend.database import db

    user = db.get_user_by_email("user@example.com")
"""
from backend.database.db import Database

# Create a module-level database instance
# This is initialized when the module is imported
db = Database()

__all__ = ['Database', 'db']
