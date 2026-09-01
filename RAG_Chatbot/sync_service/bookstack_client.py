import os
import requests
from typing import List, Dict, Any
import time


class BookstackClient:
    """
    Client for interacting with BookStack API.

    This class handles authentication and provides methods to interact with
    BookStack's API endpoints for pages, books, and other resources.
    """

    def __init__(self):
        self.base_url = os.getenv("BOOKSTACK_URL")
        self.token_id = os.getenv("BOOKSTACK_TOKEN_ID")
        self.token_secret = os.getenv("BOOKSTACK_TOKEN_SECRET")
        self._book_cache = {}

        # Set up authentication headers - BookStack uses different auth format
        self.headers = {
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Content-Type": "application/json",
        }

    def get_all_pages(self, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Get all pages from BookStack API with offset pagination.

        Args:
            max_retries: Maximum number of retry attempts per request

        Returns:
            List of dictionaries containing page information with keys:
            id, updated_at, book_id, name

        Raises:
            requests.RequestException: If API request fails after all retries
        """
        pages_by_id = {}
        url = f"{self.base_url}/api/pages"
        count = 500
        offset = 0
        total = None

        while total is None or offset < total:
            params = {"count": count, "offset": offset}

            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.RequestException:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2**attempt)

            page_data = data.get("data", [])
            total = data.get("total", len(page_data))
            if not page_data:
                break

            for page in page_data:
                page_id = page.get("id")
                if page_id is None:
                    continue
                pages_by_id[page_id] = {
                    "id": page_id,
                    "updated_at": page.get("updated_at"),
                    "book_id": page.get("book_id"),
                    "name": page.get("name"),
                }

            offset += len(page_data)

        return list(pages_by_id.values())

    def export_page_markdown(self, page_id: int) -> str:
        """Export a specific page as markdown"""
        url = f"{self.base_url}/api/pages/{page_id}/export/markdown"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        return response.text

    def get_book_metadata(self, book_id: int) -> Dict[str, Any]:
        """Get book metadata, including the first shelf name."""
        if book_id in self._book_cache:
            return self._book_cache[book_id]

        book_url = f"{self.base_url}/api/books/{book_id}"
        response = requests.get(book_url, headers=self.headers)
        response.raise_for_status()
        book_data = response.json()

        shelf_name = None
        shelves = book_data.get("shelves", [])
        if shelves and isinstance(shelves, list):
            shelf_name = shelves[0].get("name")

        metadata = {
            "book_name": book_data.get("name"),
            "shelf_name": shelf_name,
        }
        self._book_cache[book_id] = metadata
        return metadata

    def get_page_metadata(self, page_id: int) -> Dict[str, Any]:
        """Get page metadata including book and shelf information"""
        # Get page details
        page_url = f"{self.base_url}/api/pages/{page_id}"
        response = requests.get(page_url, headers=self.headers)
        response.raise_for_status()
        page_data = response.json()

        # Get book information
        book_id = page_data.get("book_id")
        book_metadata = self.get_book_metadata(book_id)

        return {
            "page_title": page_data.get("name"),
            "book_name": book_metadata.get("book_name"),
            "shelf_name": book_metadata.get("shelf_name"),
            "tags": page_data.get("tags", []),
        }

