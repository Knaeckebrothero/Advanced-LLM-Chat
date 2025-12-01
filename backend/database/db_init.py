"""
Database initialization script for the Fessi backend.

This script initializes the PostgreSQL database schema and optionally seeds it
with test data. It supports two modes:

1. Default mode: Creates tables if they don't exist (preserves existing data)
2. Force-reset mode: Drops all tables and recreates from scratch

Usage:
    # Default: Create tables if missing, preserve data
    python -m backend.database.db_init

    # Force reset: Drop all tables and recreate
    python -m backend.database.db_init --force-reset

    # With seed data: Insert test users and conversations
    python -m backend.database.db_init --seed

    # Combined: Fresh database with seed data
    python -m backend.database.db_init --force-reset --seed
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

# Constants
QUERIES_DIR = Path(__file__).parent / "queries"
SCHEMA_FILE = QUERIES_DIR / "schema.sql"
SEED_FILE = QUERIES_DIR / "seed.sql"

# Expected tables for verification
EXPECTED_TABLES = [
    "users",
    "conversations",
    "messages",
    "sessions",
    "guest_usage",
    "user_settings",
]


def setup_logging() -> logging.Logger:
    """
    Configure logging for database initialization.

    Returns:
        Logger instance configured for console output.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Initialize the Fessi PostgreSQL database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.database.db_init              # Create tables if missing
  python -m backend.database.db_init --force-reset  # Drop and recreate all tables
  python -m backend.database.db_init --seed       # Create tables and insert test data
  python -m backend.database.db_init --force-reset --seed  # Fresh database with test data
        """,
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Drop all tables and recreate from schema.sql (WARNING: deletes all data)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Insert test/example data after initialization",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host (default: from .env or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("POSTGRES_PORT", "5432")),
        help="PostgreSQL port (default: from .env or 5432)",
    )
    parser.add_argument(
        "--database",
        default=os.getenv("POSTGRES_DB", "fessi_chat"),
        help="Database name (default: from .env or fessi_chat)",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("POSTGRES_USER", "fessi"),
        help="Database user (default: from .env or fessi)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("POSTGRES_PASSWORD", ""),
        help="Database password (default: from .env)",
    )
    return parser.parse_args()


def create_database_if_not_exists(
    host: str, port: int, user: str, password: str, db_name: str, logger: logging.Logger
) -> bool:
    """
    Create the database if it doesn't exist.

    Connects to the 'postgres' system database to check for and create the
    target database. Requires appropriate PostgreSQL privileges.

    Args:
        host: PostgreSQL host.
        port: PostgreSQL port.
        user: Database user.
        password: Database password.
        db_name: Name of the database to create.
        logger: Logger instance.

    Returns:
        True if database was created, False if it already existed.

    Raises:
        psycopg2.Error: If connection or creation fails.
    """
    conn = None
    try:
        # Connect to the default 'postgres' database
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        )
        exists = cursor.fetchone() is not None

        if exists:
            logger.info(f"  ✓ Database '{db_name}' already exists")
            return False

        # Create the database
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
        )
        logger.info(f"  ✓ Created database '{db_name}'")
        return True

    finally:
        if conn:
            conn.close()


def get_engine(host: str, port: int, user: str, password: str, db_name: str):
    """
    Create a SQLAlchemy engine for the target database.

    Args:
        host: PostgreSQL host.
        port: PostgreSQL port.
        user: Database user.
        password: Database password.
        db_name: Database name.

    Returns:
        SQLAlchemy Engine instance.
    """
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url, echo=False)


def drop_all_tables(engine, logger: logging.Logger) -> None:
    """
    Drop all tables, triggers, and functions from the database.

    Tables are dropped in dependency order to respect foreign key constraints.

    Args:
        engine: SQLAlchemy engine.
        logger: Logger instance.
    """
    # Drop order respects foreign key dependencies
    drop_order = [
        "messages",
        "sessions",
        "user_settings",
        "guest_usage",
        "conversations",
        "users",
    ]

    with engine.connect() as conn:
        # First drop triggers
        logger.info("  Dropping triggers...")
        triggers = [
            ("update_conversations_timestamp", "conversations"),
            ("update_messages_timestamp", "messages"),
            ("update_user_settings_timestamp", "user_settings"),
        ]
        for trigger_name, table_name in triggers:
            try:
                conn.execute(
                    text(f'DROP TRIGGER IF EXISTS {trigger_name} ON "{table_name}"')
                )
            except Exception:
                pass  # Ignore errors if trigger doesn't exist

        # Drop functions
        logger.info("  Dropping functions...")
        conn.execute(text("DROP FUNCTION IF EXISTS update_timestamp() CASCADE"))
        conn.execute(text("DROP FUNCTION IF EXISTS update_conversation_timestamp() CASCADE"))

        # Drop tables
        logger.info("  Dropping tables...")
        for table in drop_order:
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                logger.info(f"    ✓ Dropped table '{table}'")
            except Exception as e:
                logger.warning(f"    ⚠ Could not drop table '{table}': {e}")

        conn.commit()

    logger.info("  ✓ All tables dropped")


def execute_schema_sql(engine, schema_path: Path, logger: logging.Logger) -> bool:
    """
    Execute the schema SQL file to create tables, indexes, and triggers.

    The schema uses CREATE TABLE IF NOT EXISTS, making it idempotent.

    Args:
        engine: SQLAlchemy engine.
        schema_path: Path to the schema.sql file.
        logger: Logger instance.

    Returns:
        True if successful, False otherwise.
    """
    if not schema_path.exists():
        logger.error(f"  ✗ Schema file not found: {schema_path}")
        return False

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        # Split by named blocks and execute each
        # The schema uses -- name: comments to separate sections
        with engine.connect() as conn:
            # Execute the entire schema as one script
            # PostgreSQL can handle multiple statements
            conn.execute(text(schema_sql))
            conn.commit()

        logger.info(f"  ✓ Executed schema from {schema_path.name}")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error executing schema: {e}")
        return False


def insert_seed_data(engine, seed_path: Path, logger: logging.Logger) -> bool:
    """
    Execute the seed SQL file to insert test data.

    The seed data uses ON CONFLICT DO NOTHING, making it safe to run multiple times.

    Args:
        engine: SQLAlchemy engine.
        seed_path: Path to the seed.sql file.
        logger: Logger instance.

    Returns:
        True if successful, False otherwise.
    """
    if not seed_path.exists():
        logger.warning(f"  ⚠ Seed file not found: {seed_path}")
        return False

    try:
        with open(seed_path, "r", encoding="utf-8") as f:
            seed_sql = f.read()

        with engine.connect() as conn:
            conn.execute(text(seed_sql))
            conn.commit()

            # Count inserted seed data
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()

            result = conn.execute(text("SELECT COUNT(*) FROM conversations"))
            conv_count = result.scalar()

        logger.info(f"  ✓ Inserted seed data ({user_count} users, {conv_count} conversations)")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error inserting seed data: {e}")
        return False


def verify_schema(engine, logger: logging.Logger) -> bool:
    """
    Verify that all expected tables exist in the database.

    Args:
        engine: SQLAlchemy engine.
        logger: Logger instance.

    Returns:
        True if all tables exist, False otherwise.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    all_present = True
    for table in EXPECTED_TABLES:
        if table in existing_tables:
            logger.info(f"    ✓ Table '{table}' exists")
        else:
            logger.error(f"    ✗ Table '{table}' missing")
            all_present = False

    return all_present


def initialize_database(args: argparse.Namespace, logger: logging.Logger) -> bool:
    """
    Main database initialization logic.

    Performs the following steps:
    1. Create database if it doesn't exist
    2. If --force-reset: drop all existing tables
    3. Execute schema.sql to create tables
    4. If --seed: insert test data
    5. Verify schema

    Args:
        args: Parsed command line arguments.
        logger: Logger instance.

    Returns:
        True if initialization successful, False otherwise.
    """
    logger.info("")
    logger.info("=== Database Initialization ===")
    logger.info("")

    # Step 1: Create database if not exists
    logger.info("[1/4] Checking database...")
    try:
        create_database_if_not_exists(
            args.host, args.port, args.user, args.password, args.database, logger
        )
    except Exception as e:
        logger.error(f"  ✗ Failed to check/create database: {e}")
        logger.info("")
        logger.info("  Hint: Make sure PostgreSQL is running and credentials are correct.")
        logger.info(f"  Tried to connect to: {args.host}:{args.port} as '{args.user}'")
        return False

    # Get engine for the target database
    engine = get_engine(args.host, args.port, args.user, args.password, args.database)

    # Step 2: Force reset if requested
    if args.force_reset:
        logger.info("")
        logger.info("[2/4] Force reset - dropping all tables...")
        logger.warning("  ⚠ WARNING: All existing data will be deleted!")
        drop_all_tables(engine, logger)
    else:
        logger.info("")
        logger.info("[2/4] Preserving existing data (use --force-reset to drop tables)")

    # Step 3: Execute schema
    logger.info("")
    logger.info("[3/4] Creating tables from schema...")
    if not execute_schema_sql(engine, SCHEMA_FILE, logger):
        return False

    # Step 4: Insert seed data if requested
    logger.info("")
    if args.seed:
        logger.info("[4/4] Inserting seed data...")
        if not insert_seed_data(engine, SEED_FILE, logger):
            logger.warning("  ⚠ Seed data insertion had issues, but continuing...")
    else:
        logger.info("[4/4] Skipping seed data (use --seed to insert test data)")

    # Verify schema
    logger.info("")
    logger.info("Verifying schema...")
    if not verify_schema(engine, logger):
        logger.error("")
        logger.error("  ✗ Schema verification failed!")
        return False

    logger.info("")
    logger.info("=== Database Initialization Complete ===")
    logger.info("")

    if args.seed:
        logger.info("Test credentials:")
        logger.info("  - test@example.com")
        logger.info("  - admin@example.com")
        logger.info("  - demo@example.com")
        logger.info("")

    return True


def main() -> int:
    """
    Main entry point for database initialization.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger = setup_logging()
    args = parse_args()

    try:
        success = initialize_database(args, logger)
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Initialization cancelled by user.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
