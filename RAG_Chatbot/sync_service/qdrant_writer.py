import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
)

def _get_qdrant_client() -> QdrantClient:
    """
    Helper to return a Qdrant client configured via environment variables.
    """
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    return QdrantClient(url=qdrant_url)


def upsert_chunks(chunks: List[Dict[str, Any]]) -> None:
    """
    Upsert a batch of chunks into the Qdrant knowledge_base collection.
    
    Args:
        chunks (List[Dict[str, Any]]): List of chunk dictionaries. 
            Each chunk dict should contain:
            - page_id (int): Page identifier
            - chunk_index (int): Index of chunk within the page
            - dense_vector (List[float]): Dense embedding values
            - sparse_vector (Dict[str, List]): Sparse embedding with 'indices' and 'values'
            - payload (Dict[str, Any]): Metadata about the chunk
    """
    if not chunks:
        return
        
    client = _get_qdrant_client()
    collection_name = os.getenv("QDRANT_COLLECTION", "knowledge_base")
    
    points = []
    for chunk in chunks:
        page_id = chunk["page_id"]
        chunk_idx = chunk["chunk_index"]
        
        # Determine UUID5 using predefined DNS namespace and composite string
        unique_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{page_id}_{chunk_idx}"))
        
        point = PointStruct(
            id=unique_id,
            vector={
                "dense": chunk["dense_vector"],
                "sparse": chunk["sparse_vector"]
            },
            payload=chunk["payload"]
        )
        points.append(point)
        
    # Perform batch upsert
    client.upsert(
        collection_name=collection_name, 
        points=points
    )


def delete_page(page_id: int) -> None:
    """
    Delete all chunks belonging to a specific page_id.
    
    Args:
        page_id (int): The ID of the page whose chunks need to be deleted.
    """
    client = _get_qdrant_client()
    collection_name = os.getenv("QDRANT_COLLECTION", "knowledge_base")
    
    # Delete based on exactly matching the page_id
    client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="page_id",
                    match=MatchValue(value=page_id)
                )
            ]
        )
    )
