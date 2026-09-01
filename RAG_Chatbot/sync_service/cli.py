import logging
import argparse
from dotenv import load_dotenv

# Provide .env variables before importing other modules that evaluate them
load_dotenv()

from .sync import run_sync

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyncCLI")

def main() -> None:
    """Main CLI entry point for manually triggering synchronization"""
    parser = argparse.ArgumentParser(description="Sync Service CLI - RAG Knowledge Base")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="Sync mode: 'full' synchronizes all items, 'incremental' only synchronizes delta changes (default: incremental)"
    )
    parser.add_argument(
        "--page-id", 
        type=int, 
        help="Specific page ID to exclusively sync. Ignores other changes if provided."
    )
    parser.add_argument(
        "--shelf",
        action="append",
        dest="shelf_names",
        help="BookStack shelf name to sync. Can be provided multiple times. Also supports SYNC_SHELVES in .env."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report pages that would be added, updated, or deleted. Does not modify Qdrant."
    )

    args = parser.parse_args()

    # Inform explicitly if page ID is used
    if args.page_id:
        logger.info(f"Manual Sync requested for a specific page: {args.page_id}")
    else:
        logger.info(f"Manual Sync requested in {args.mode} mode.")

    # Call the orchestrator
    try:
        run_sync(mode=args.mode, page_id=args.page_id, shelf_names=args.shelf_names, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Manual Sync script failed abruptly: {str(e)}")

if __name__ == "__main__":
    main()
