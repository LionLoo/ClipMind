# Purpose:
#   Connect query encoding + FAISS search + DB lookup
#   Take a text query and return ranked Item results by semantic similarity

from typing import List, Tuple
from sqlmodel import select
import sys
from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.store import IndexStore
from app.search.encoder import encode_text_to_vector, VECTOR_DIM
from app.core import config

def semantic_search(query_text: str, top_k: int = None):
    """
    Search for items semantically similar to query_text

    -query_text: the search query
    -top_k: number of results to return (defaults to config.top_k_results)

    returns:
        list of (item, distance_score) tuple, ordered by relevance (lowest distance first)
    """

    if top_k is None:
        top_k = config.top_k_results

    query_vector = encode_text_to_vector(query_text)
    store = IndexStore(vector_dimension=VECTOR_DIM)

    if store.index.ntotal == 0:
        print("[WARN] FAISS index is empty! can rebuild with rebuild_from_db.py")
        return []

    distances, positions, item_ids = store.search(query_vector, top_k)

    init_db()
    results = []

    with get_session() as session:
        for item_id, distance in zip(item_ids, distances[0]):
            if item_id == -1:
                continue

            #gets item from DB
            statement = select(Item).where(Item.id == item_id)
            item = session.exec(statement).first()

            if item:
                results.append((item, float(distance)))


    return results

def main():
    """
    Test semantic search
    use: python -m app.search.semantic_search
    """
    if len(sys.argv) < 2:
        print("Usage: python -m app.search.semantic_search <query> [top_k]")
        sys.exit(1)

    query = sys.argv[1]
    if len(sys.argv) >= 3:
        try:
            top_k = int(sys.argv[2])
        except ValueError:
            print("[WARN] Invalid limit, using config.top_k_results")
            top_k = config.top_k_results
    else:
        top_k = config.top_k_results

    print(f"[SEARCH] searching for: '{query}' (top {top_k} results)")
    print("=" * 60)

    results = semantic_search(query, top_k)

    if not results:
        print("[RESULT] no results found")
        return

    print(f"Found {len(results)} result(s):\n")

    for idx, (item, distance) in enumerate(results, 1):
        #shorten text if too long
        preview = item.text[:80] + "..." if len(item.text) > 80 else item.text

        print(f"{idx}. Item #{item.id} (score: {distance:.4f})")
        print(f"   Time: {item.readable_time}")
        print(f"   Text: {repr(preview)}")
        print()

if __name__ == "__main__":
    main()