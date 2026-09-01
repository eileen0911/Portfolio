import os
import logging
from typing import Literal
from .bookstack_client import BookstackClient
from .chunker import chunk_markdown
from .bm25_encoder import BM25Encoder
from .embedder import embed_batch
from .qdrant_writer import upsert_chunks, delete_page
from .change_detector import get_changed_pages

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SyncOrchestrator")


def _normalize_shelf_name(value: str) -> str:
    return value.strip().casefold()


def _parse_shelf_names(shelf_names: list[str] | None = None) -> list[str]:
    values = shelf_names or []
    env_value = os.getenv("SYNC_SHELVES", "")
    if env_value:
        values = values + [item for item in env_value.split(",")]
    return [item.strip() for item in values if item and item.strip()]


def _filter_pages_by_shelf(
    bookstack: BookstackClient,
    pages: list[dict],
    shelf_names: list[str],
) -> list[dict]:
    if not shelf_names:
        return pages

    target_shelves = {_normalize_shelf_name(name) for name in shelf_names}
    filtered_pages = []

    for page in pages:
        book_id = page.get("book_id")
        if not book_id:
            continue

        try:
            book_metadata = bookstack.get_book_metadata(book_id)
        except Exception as e:
            logger.error(
                f"Failed to fetch book metadata for book {book_id}; skipping page {page.get('id')}: {str(e)}"
            )
            continue

        shelf_name = book_metadata.get("shelf_name") or ""
        if _normalize_shelf_name(shelf_name) in target_shelves:
            page["book_name"] = book_metadata.get("book_name")
            page["shelf_name"] = shelf_name
            filtered_pages.append(page)

    return filtered_pages

def _format_page_for_log(page_id: int, pages_map: dict[int, dict]) -> str:
    page = pages_map.get(page_id, {})
    name = page.get("name") or page.get("page_title")
    if name:
        return f"{page_id} ({name})"
    return str(page_id)


def _log_dry_run_plan(pages_to_process: dict[str, list[int]], pages_map: dict[int, dict]) -> None:
    for action in ("added", "updated", "deleted"):
        page_ids = pages_to_process[action]
        if page_ids:
            page_list = ", ".join(_format_page_for_log(pid, pages_map) for pid in page_ids)
        else:
            page_list = "none"
        logger.info(f"Dry Run {action}: {page_list}")


def run_sync(
    mode: Literal["full", "incremental"] = "incremental",
    page_id: int = None,
    shelf_names: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """
    Run the synchronization process between BookStack and Qdrant.

    Args:
        mode: Synchronization mode - 'full' or 'incremental'
        page_id: Optional explicit page_id to synchronize
        shelf_names: Optional BookStack shelf names to limit sync scope
        dry_run: If true, only report the sync plan without changing Qdrant
    """
    logger.info(f"Starting Knowledge Base Sync in '{mode}' mode...")

    # Initialize components
    bookstack = BookstackClient()
    bm25 = BM25Encoder()
    # Paths for model saving
    bm25_path = os.path.join(os.path.dirname(__file__), "bm25_model.pkl")
    target_shelves = _parse_shelf_names(shelf_names)

    if target_shelves:
        logger.info(f"Shelf filter enabled: {', '.join(target_shelves)}")

    if page_id is not None:
        logger.info(f"Manual override: Target syncing single page ID {page_id}")
        pages_to_process = {"added": [page_id], "updated": [], "deleted": []}
        bs_pages_map = {page_id: {"updated_at": ""}}
    else:
        # Get all pages from BookStack
        logger.info("Fetching all pages metadata from BookStack...")
        try:
            bookstack_pages = bookstack.get_all_pages()
            logger.info(f"Found {len(bookstack_pages)} pages in BookStack")
            bookstack_pages = _filter_pages_by_shelf(bookstack, bookstack_pages, target_shelves)
            if target_shelves:
                logger.info(f"Found {len(bookstack_pages)} pages after shelf filtering")
        except Exception as e:
            logger.error(f"Failed to fetch pages from BookStack: {str(e)}")
            return

        # Determine which pages to process
        if mode == "incremental":
            changed_pages = get_changed_pages(bookstack_pages, shelf_names=target_shelves)
            pages_to_process = changed_pages
        else:
            # Full sync - process all scoped pages as added, nothing updated, nothing deleted
            pages_to_process = {
                "added": [p["id"] for p in bookstack_pages],
                "updated": [],
                "deleted": []
            }

        added_count = len(pages_to_process["added"])
        updated_count = len(pages_to_process["updated"])
        deleted_count = len(pages_to_process["deleted"])

        logger.info(f"Sync Plan: {added_count} to add, {updated_count} to update, {deleted_count} to delete.")

        bs_pages_map = {p["id"]: p for p in bookstack_pages}

    if dry_run:
        if page_id is not None:
            added_count = len(pages_to_process["added"])
            updated_count = len(pages_to_process["updated"])
            deleted_count = len(pages_to_process["deleted"])
            logger.info(f"Sync Plan: {added_count} to add, {updated_count} to update, {deleted_count} to delete.")
        _log_dry_run_plan(pages_to_process, bs_pages_map)
        logger.info("Dry run completed. No Qdrant writes, deletes, embeddings, or BM25 updates were performed.")
        return

    # Load BM25 model - use existing trained model only for incremental
    corpus_for_bm25 = []  # Collect corpus for building NEW BM25 model
    bm25_loaded = False

    if mode == "incremental" and os.path.exists(bm25_path):
        logger.info("Loading existing BM25 encoder model for incremental sync...")
        bm25 = BM25Encoder.load(bm25_path)
        bm25_loaded = True
    elif mode == "full" and os.path.exists(bm25_path):
        # Full sync 2nd pass: load trained BM25 to properly encode sparse vectors
        logger.info("Full sync 2nd pass: Loading trained BM25 encoder...")
        bm25 = BM25Encoder.load(bm25_path)
        bm25_loaded = True
    else:
        # Full sync 1st pass or no BM25 exists: build new BM25 from scratch
        logger.info("Full sync 1st pass: Building BM25 from scratch...")

    # Process additions and updates
    pages_to_upsert = pages_to_process["added"] + pages_to_process["updated"]
    for page_id in pages_to_upsert:
        try:
            metadata = bookstack.get_page_metadata(page_id)
            markdown_content = bookstack.export_page_markdown(page_id)
            chunks = chunk_markdown(markdown_content)

            # Only collect corpus when building NEW BM25 model (not using existing)
            if not bm25_loaded:
                corpus_for_bm25.append(markdown_content)

            # Extract texts for dense batch embedding
            chunk_texts = [c["chunk_text"] for c in chunks]
            dense_vectors = embed_batch(chunk_texts)

            # Map updated timestamp
            updated_at_str = bs_pages_map[page_id].get("updated_at", "")

            # Construct final chunk dict compatible with upsert_chunks
            formatted_chunks = []
            for i, chunk in enumerate(chunks):
                # sparse vector generated on the fly. Fallback if model not trained yet
                sparse_vector = bm25.encode_document(chunk["chunk_text"]) if bm25.vocab else {"indices": [], "values": []}

                payload = {
                    "source_category": metadata.get("book_name", "default").lower(),
                    "page_id": page_id,
                    "page_title": metadata.get("page_title", ""),
                    "book_name": metadata.get("book_name", ""),
                    "shelf_name": metadata.get("shelf_name", ""),
                    "tags": metadata.get("tags", []),
                    "chunk_index": chunk["chunk_index"],
                    "chunk_text": chunk["chunk_text"],
                    "synced_at": updated_at_str
                }

                formatted_chunks.append({
                    "page_id": page_id,
                    "chunk_index": chunk["chunk_index"],
                    "dense_vector": dense_vectors[i],
                    "sparse_vector": sparse_vector,
                    "payload": payload
                })

            # Upsert into DB
            if formatted_chunks:
                # To prevent zombie chunks (e.g. if an article shrinks from 10 to 3 chunks, chunks 4-10 would linger),
                # we must delete the old chunks for this page first before upserting the new ones.
                delete_page(page_id)
                upsert_chunks(formatted_chunks)

            logger.info(f"Successfully processed page {page_id} (Upserted {len(formatted_chunks)} chunks)")

        except Exception as e:
            logger.error(f"Error processing page {page_id}: {str(e)}", exc_info=True)
            continue

    # Execute Deletions
    for page_id in pages_to_process["deleted"]:
        try:
            delete_page(page_id)
            logger.info(f"Deleted page {page_id} from Qdrant")
        except Exception as e:
            logger.error(f"Error deleting page {page_id}: {str(e)}", exc_info=True)

    # Finally, if mode == "full" and we built a NEW BM25 model (not loaded), save it
    if mode == "full" and corpus_for_bm25 and not bm25_loaded:
        logger.info("Fitting and Saving BM25 Model from collected full corpus...")
        bm25.fit(corpus_for_bm25)
        bm25.save(bm25_path)
        logger.info(f"BM25 Model updated and saved at {bm25_path}")

    logger.info("Sync Job completed successfully.")
