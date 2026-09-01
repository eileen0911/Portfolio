from typing import List, Dict, Any
import os
from qdrant_client import QdrantClient


def _normalize_shelf_name(value: str) -> str:
    return value.strip().casefold()


def get_changed_pages(
    bookstack_pages: List[Dict[str, Any]],
    shelf_names: list[str] | None = None,
) -> Dict[str, List[int]]:
    """
    Determine which pages have been added, updated, or deleted
    by comparing BookStack records with Qdrant collection payload.

    Args:
        bookstack_pages: List of pages from BookStack API (must include 'id' and 'updated_at')
        shelf_names: Optional shelf names used to scope Qdrant deletion detection

    Returns:
        Dictionary with 'added', 'updated', 'deleted' page IDs.
    """
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)

    qdrant_data = {}
    collection_name = os.getenv("QDRANT_COLLECTION", "knowledge_base")
    target_shelves = {_normalize_shelf_name(name) for name in (shelf_names or []) if name}

    try:
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                scroll_filter=None,
                limit=1000,
                with_payload=["page_id", "synced_at", "shelf_name"],
                with_vectors=False,
                offset=offset
            )
            for record in records:
                if not record.payload or "page_id" not in record.payload:
                    continue

                shelf_name = record.payload.get("shelf_name") or ""
                if target_shelves and _normalize_shelf_name(shelf_name) not in target_shelves:
                    continue

                pid = record.payload["page_id"]
                # Due to chunks, page_id occurs multiple times.
                # We just take the synced_at timestamp of the first chunk we see.
                if pid not in qdrant_data:
                    qdrant_data[pid] = record.payload.get("synced_at", "")
            if offset is None:
                break
    except Exception:
        # Expected if collection doesn't exist yet
        pass

    added = []
    updated = []
    deleted = []

    bs_pages_map = {p["id"]: p for p in bookstack_pages}

    # 1. Check added and updated
    for bs_id, bs_page in bs_pages_map.items():
        bs_updated_at = bs_page.get("updated_at", "")
        # Standardize strings if possible, assuming alphabetical timestamp strings match correctly
        # (BookStack returns YYYY-MM-DD HH:MM:SS or ISO-8601).

        if bs_id not in qdrant_data:
            added.append(bs_id)
        else:
            q_synced_at = qdrant_data.get(bs_id, "")
            # Direct string comparison works for ISO 8601 / standard YYYY-MM-DD formats
            if bs_updated_at > q_synced_at:
                updated.append(bs_id)

    # 2. Check deleted
    for q_id in qdrant_data.keys():
        if q_id not in bs_pages_map:
            deleted.append(q_id)

    return {"added": added, "updated": updated, "deleted": deleted}
