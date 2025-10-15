# Purpose:
#   Connect query encoding + FAISS search + DB lookup
#   Take a text query and return ranked Item results by semantic similarity
#   Added support for text search, image search, filtering by source AND TIME

from typing import List, Tuple, Literal, Optional
from sqlmodel import select
import sys
from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.vector_store import DualVectorStore
from app.search.encoder import encode_text_to_vector, VECTOR_DIM
from app.search.clip_encoder import encode_text_for_image_search, IMAGE_VECTOR_DIM
from app.core import config

SearchMode = Literal["all", "text", "images"]


def semantic_search(
        query_text: str,
        top_k: int = None,
        mode: SearchMode = "all",
        source_filter: Optional[str] = None,
        after_timestamp: Optional[int] = None
) -> List[Tuple[Item, float]]:
    """
    Search for items semantically similar to query_text

    Args:
        query_text: the search query
        top_k: number of results to return (defaults to config.top_k_results)
        mode: "all" (both images and text)", "text", "images"
        source_filter: Filter by source type ("clipboard" or "screenshot")
        after_timestamp: Only return items created after this Unix timestamp

    Returns:
        list of (item, distance_score) tuple, ordered by relevance (lowest distance first)
    """
    if top_k is None:
        top_k = config.top_k_results

    init_db()
    store = DualVectorStore(text_dim=VECTOR_DIM, image_dim=IMAGE_VECTOR_DIM)
    results = []

    # Search text vectors
    if mode in ["all", "text"]:
        if store.text_index.ntotal > 0:
            query_vector = encode_text_to_vector(query_text)
            distances, positions, item_ids = store.search_text(query_vector,
                                                               top_k * 3)  # Get more results for filtering

            with get_session() as session:
                for item_id, distance in zip(item_ids, distances[0]):
                    if item_id == -1:
                        continue

                    # Build query with filters
                    statement = select(Item).where(Item.id == item_id)

                    # Apply time filter
                    if after_timestamp is not None:
                        statement = statement.where(Item.created_ts >= after_timestamp)

                    # Apply source filter
                    if source_filter is not None:
                        statement = statement.where(Item.source == source_filter)

                    item = session.exec(statement).first()

                    if item:
                        results.append((item, float(distance), "text"))

    # Search image vectors
    if mode in ["all", "images"]:
        if store.image_index.ntotal > 0:
            # Encode with CLIP
            query_vector = encode_text_for_image_search(query_text)
            distances, positions, item_ids = store.search_image(query_vector,
                                                                top_k * 3)  # Get more results for filtering

            with get_session() as session:
                for item_id, distance in zip(item_ids, distances[0]):
                    if item_id == -1:
                        continue

                    # Build query with filters
                    statement = select(Item).where(Item.id == item_id)
                    statement = statement.where(Item.source == "screenshot")  # Images are always screenshots

                    # Apply time filter
                    if after_timestamp is not None:
                        statement = statement.where(Item.created_ts >= after_timestamp)

                    # Apply source filter (redundant but consistent)
                    if source_filter is not None:
                        statement = statement.where(Item.source == source_filter)

                    item = session.exec(statement).first()

                    if item:
                        results.append((item, float(distance), "image"))

    # Sort by distance (lower = better)
    results.sort(key=lambda x: x[1])

    # Remove duplicates (possible that it appears in image and text)
    seen_ids = set()
    unique_results = []
    for item, distance, search_type in results[:top_k * 2]:  # Look at more results before deduping
        if item.id not in seen_ids:
            seen_ids.add(item.id)
            unique_results.append((item, distance))

    return unique_results[:top_k]


def search_images_only(query_text: str, top_k: int = None, after_timestamp: Optional[int] = None) -> List[
    Tuple[Item, float]]:
    """
    Search only screenshots using image embeddings
    eg: "beach sunset" finds screenshots of beaches
    """
    return semantic_search(query_text, top_k=top_k, mode="images", source_filter="screenshot",
                           after_timestamp=after_timestamp)


def search_text_only(query_text: str, top_k: int = None, after_timestamp: Optional[int] = None) -> List[
    Tuple[Item, float]]:
    """
    Search only text content (clipboard items + screenshot OCR)
    """
    return semantic_search(query_text, top_k=top_k, mode="text", after_timestamp=after_timestamp)


def search_clipboard_only(query_text: str, top_k: int = None, after_timestamp: Optional[int] = None) -> List[
    Tuple[Item, float]]:
    """
    Search only clipboard items
    """
    return semantic_search(query_text, top_k=top_k, mode="text", source_filter="clipboard",
                           after_timestamp=after_timestamp)


def main():
    """CLI for testing semantic search"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.search.semantic_search <query> [top_k] [mode] [after_timestamp]")
        print("  mode: all (default), text, images, clipboard")
        print("  after_timestamp: Unix timestamp to filter by time")
        print("Example: python -m app.search.semantic_search 'beach sunset' 5 images")
        sys.exit(1)

    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) >= 3 else config.top_k_results
    mode = sys.argv[3] if len(sys.argv) >= 4 else "all"
    after_timestamp = int(sys.argv[4]) if len(sys.argv) >= 5 else None

    print(f"[SEARCH] Query: '{query}' (mode: {mode}, top {top_k} results)")
    if after_timestamp:
        from datetime import datetime
        print(f"[SEARCH] Time filter: After {datetime.fromtimestamp(after_timestamp)}")
    print("=" * 60)

    # Use appropriate function
    if mode == "images":
        results = search_images_only(query, top_k, after_timestamp)
    elif mode == "clipboard":
        results = search_clipboard_only(query, top_k, after_timestamp)
    elif mode == "text":
        results = search_text_only(query, top_k, after_timestamp)
    else:
        results = semantic_search(query, top_k, mode="all", after_timestamp=after_timestamp)

    if not results:
        print("[RESULT] No results found.")
        return

    print(f"Found {len(results)} result(s):\n")

    for idx, (item, distance) in enumerate(results, 1):
        preview = item.text[:80] + "..." if len(item.text) > 80 else item.text

        print(f"{idx}. Item #{item.id} (score: {distance:.4f}) [{item.source.upper()}]")
        print(f"   Time: {item.readable_time}")
        print(f"   Text: {repr(preview)}")

        if item.blob_uri:
            print(f"   Image: {item.blob_uri}")

        print()


if __name__ == "__main__":
    main()