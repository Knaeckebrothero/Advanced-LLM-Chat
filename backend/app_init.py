"""
Application initialization script for the Fessi backend.

This script initializes the complete application environment including:
- Filesystem directory structure
- Environment configuration (.env file)
- SSL certificates for development
- PostgreSQL database (via db_init.py)

Usage:
    # Initialize everything (filesystem + database)
    python backend/app_init.py

    # Force reset everything (delete .filesystem, recreate database)
    python backend/app_init.py --force-reset

    # With seed data
    python backend/app_init.py --seed

    # Skip database initialization
    python backend/app_init.py --skip-db

    # Setup filesystem only (no database, no certs)
    python backend/app_init.py --setup-only
"""
import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

# Add project root to path so we can import backend modules
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

# Constants
BASE_DIR = Path(__file__).parent.parent  # Project root
FILESYSTEM_DIR = Path(os.getenv("FILESYSTEM_PATH", ".filesystem"))
DEVCERTS_DIR = Path("devcerts")
ENV_EXAMPLE = BASE_DIR / ".env.example"
ENV_FILE = BASE_DIR / ".env"


def setup_logging() -> logging.Logger:
    """
    Configure logging for application initialization.

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
        description="Initialize the Fessi backend application.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/app_init.py                    # Initialize everything
  python backend/app_init.py --force-reset      # Reset and reinitialize
  python backend/app_init.py --seed             # Initialize with test data
  python backend/app_init.py --skip-db          # Skip database setup
  python backend/app_init.py --setup-only       # Filesystem only
        """,
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Delete .filesystem/ and reset database (WARNING: deletes all data)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Insert test/example data into database",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip database initialization",
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Only create filesystem structure (no database, no certs)",
    )
    parser.add_argument(
        "--no-certs",
        action="store_true",
        help="Skip SSL certificate generation",
    )
    return parser.parse_args()


def get_filesystem_dirs() -> list[Path]:
    """
    Get list of directories to create for the application.

    Returns:
        List of Path objects for required directories.
    """
    return [
        FILESYSTEM_DIR,
        FILESYSTEM_DIR / "logs",
        FILESYSTEM_DIR / "uploads",
        FILESYSTEM_DIR / "exports",
    ]


def setup_filesystem(logger: logging.Logger, force_reset: bool = False) -> bool:
    """
    Create the required directory structure for the application.

    Args:
        logger: Logger instance.
        force_reset: If True, delete existing .filesystem/ first.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Force reset if requested
        if force_reset and FILESYSTEM_DIR.exists():
            logger.warning(f"  Deleting existing {FILESYSTEM_DIR}/...")
            shutil.rmtree(FILESYSTEM_DIR)
            logger.info(f"  ✓ Deleted {FILESYSTEM_DIR}/")

        # Create directories
        dirs = get_filesystem_dirs()
        created_count = 0

        for directory in dirs:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"  ✓ Created {directory}/")
                created_count += 1
            else:
                logger.info(f"  ✓ {directory}/ already exists")

        return True

    except Exception as e:
        logger.error(f"  ✗ Error setting up filesystem: {e}")
        return False


def setup_env_file(logger: logging.Logger) -> bool:
    """
    Copy .env.example to .env if .env doesn't exist.

    Args:
        logger: Logger instance.

    Returns:
        True if successful, False otherwise.
    """
    try:
        if ENV_FILE.exists():
            logger.info(f"  ✓ {ENV_FILE.name} already exists")
            return True

        if not ENV_EXAMPLE.exists():
            logger.warning(f"  ⚠ {ENV_EXAMPLE.name} not found, skipping .env creation")
            return True

        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        logger.info(f"  ✓ Created {ENV_FILE.name} from {ENV_EXAMPLE.name}")
        logger.warning("  ⚠ Remember to configure POSTGRES_PASSWORD in .env!")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error setting up .env file: {e}")
        return False


def setup_ssl_certificates(logger: logging.Logger) -> bool:
    """
    Generate development SSL certificates using trustme.

    Args:
        logger: Logger instance.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Check if certificates already exist
        cert_file = DEVCERTS_DIR / "server.pem"
        key_file = DEVCERTS_DIR / "server.key"

        if cert_file.exists() and key_file.exists():
            logger.info(f"  ✓ SSL certificates already exist in {DEVCERTS_DIR}/")
            return True

        # Import and run the certificate setup
        from backend.utils.certificates import setup_development_certificates

        cert_path, key_path = setup_development_certificates()
        logger.info(f"  ✓ Generated SSL certificates in {DEVCERTS_DIR}/")
        logger.info(f"    - {Path(cert_path).name}")
        logger.info(f"    - {Path(key_path).name}")
        logger.info(f"    - ca.pem")
        return True

    except ImportError as e:
        logger.error(f"  ✗ Could not import certificates module: {e}")
        logger.info("  Hint: Make sure 'trustme' is installed: pip install trustme")
        return False
    except Exception as e:
        logger.error(f"  ✗ Error generating SSL certificates: {e}")
        return False


def run_db_init(logger: logging.Logger, force_reset: bool = False, seed: bool = False) -> bool:
    """
    Run the database initialization script.

    Args:
        logger: Logger instance.
        force_reset: If True, drop all tables and recreate.
        seed: If True, insert test data.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Import db_init module
        from backend.database import db_init

        # Create args namespace to match db_init expectations
        class DbInitArgs:
            pass

        args = DbInitArgs()
        args.host = os.getenv("POSTGRES_HOST", "localhost")
        args.port = int(os.getenv("POSTGRES_PORT", "5432"))
        args.database = os.getenv("POSTGRES_DB", "fessi_chat")
        args.user = os.getenv("POSTGRES_USER", "fessi")
        args.password = os.getenv("POSTGRES_PASSWORD", "")
        args.force_reset = force_reset
        args.seed = seed

        # Create a sub-logger for db_init
        db_logger = logging.getLogger("db_init")
        db_logger.setLevel(logging.INFO)

        # Run initialization
        success = db_init.initialize_database(args, db_logger)
        return success

    except ImportError as e:
        logger.error(f"  ✗ Could not import db_init module: {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Error running database initialization: {e}")
        return False


def verify_setup(logger: logging.Logger, skip_db: bool = False, skip_certs: bool = False) -> bool:
    """
    Verify that all components are properly initialized.

    Args:
        logger: Logger instance.
        skip_db: Skip database verification.
        skip_certs: Skip certificate verification.

    Returns:
        True if verification passes, False otherwise.
    """
    all_ok = True

    # Check directories
    for directory in get_filesystem_dirs():
        if directory.exists():
            logger.info(f"  ✓ Directory {directory}/ exists")
        else:
            logger.error(f"  ✗ Directory {directory}/ missing")
            all_ok = False

    # Check .env file
    if ENV_FILE.exists():
        logger.info(f"  ✓ Environment file {ENV_FILE.name} exists")
    else:
        logger.warning(f"  ⚠ Environment file {ENV_FILE.name} missing")

    # Check SSL certificates
    if not skip_certs:
        cert_file = DEVCERTS_DIR / "server.pem"
        key_file = DEVCERTS_DIR / "server.key"
        if cert_file.exists() and key_file.exists():
            logger.info(f"  ✓ SSL certificates exist in {DEVCERTS_DIR}/")
        else:
            logger.warning(f"  ⚠ SSL certificates missing in {DEVCERTS_DIR}/")

    # Check database connection
    if not skip_db:
        try:
            from backend.database import db
            # Try to get engine - this verifies connection config is valid
            if db.engine:
                logger.info("  ✓ Database connection configured")
            else:
                logger.warning("  ⚠ Database connection not configured")
        except Exception as e:
            logger.warning(f"  ⚠ Could not verify database: {e}")

    return all_ok


def main() -> int:
    """
    Main entry point for application initialization.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger = setup_logging()
    args = parse_args()

    logger.info("")
    logger.info("=== Fessi Backend Initialization ===")
    logger.info("")

    total_steps = 5
    if args.setup_only:
        total_steps = 2
    elif args.skip_db:
        total_steps = 4
    elif args.no_certs:
        total_steps = 4

    current_step = 0

    # Step 1: Setup filesystem
    current_step += 1
    logger.info(f"[{current_step}/{total_steps}] Setting up filesystem...")
    if not setup_filesystem(logger, args.force_reset):
        logger.error("")
        logger.error("Failed to setup filesystem. Aborting.")
        return 1

    # Step 2: Setup .env file
    current_step += 1
    logger.info("")
    logger.info(f"[{current_step}/{total_steps}] Setting up environment...")
    if not setup_env_file(logger):
        logger.error("")
        logger.error("Failed to setup environment file. Aborting.")
        return 1

    # Exit early if setup-only
    if args.setup_only:
        logger.info("")
        logger.info("=== Setup Complete (filesystem only) ===")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Configure .env file with your PostgreSQL credentials")
        logger.info("  2. Run: python backend/app_init.py")
        return 0

    # Step 3: Setup SSL certificates
    if not args.no_certs:
        current_step += 1
        logger.info("")
        logger.info(f"[{current_step}/{total_steps}] Setting up SSL certificates...")
        if not setup_ssl_certificates(logger):
            logger.warning("")
            logger.warning("SSL certificate setup failed, but continuing...")

    # Step 4: Initialize database
    if not args.skip_db:
        current_step += 1
        logger.info("")
        logger.info(f"[{current_step}/{total_steps}] Initializing database...")
        if not run_db_init(logger, args.force_reset, args.seed):
            logger.error("")
            logger.error("Database initialization failed. Aborting.")
            return 1

    # Step 5: Verify setup
    current_step += 1
    logger.info("")
    logger.info(f"[{current_step}/{total_steps}] Verifying setup...")
    verify_setup(logger, args.skip_db, args.no_certs)

    # Success message
    logger.info("")
    logger.info("=== Initialization Complete ===")
    logger.info("")
    logger.info("To start the backend:")
    logger.info("  python start_backend.py")
    logger.info("")

    if args.seed:
        logger.info("Test credentials (from seed data):")
        logger.info("  - test@example.com")
        logger.info("  - admin@example.com")
        logger.info("  - demo@example.com")
        logger.info("")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("")
        print("Initialization cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
