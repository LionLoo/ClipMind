# Purpose:
# Read all saved items from DB, turn text into vectors
# add vectors to FAISS index, save the index to disk
# FIXED: Uses DualVectorStore instead of old IndexStore

from typing import List
from sqlmodel import select

from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.vector_store import DualVectorStore
from app.search.encoder import encode_many_texts, VECTOR_DIM
from app.search.clip_encoder import encode_image, IMAGE_VECTOR_DIM


def read_all_items() -> List[Item]:
    """Load all items from DB"""
    init_db()
    with get_session() as session:
        statement = select(Item).order_by(Item.id.asc())
        rows: List[Item] = session.exec(statement).all()
        return rows


def rebuild_index(batchsize: int = 1024):
    """
    Build fresh FAISS indexes from every row in DB
    WARNING: replaces whatever was there before
    """
    # Load rows from DB
    rows = read_all_items()
    if not rows:
        print("No rows found in DB")
        return

    total = len(rows)
    print(f"Found {len(rows)} row(s). Encoding into vectors with batchsize={batchsize}")

    # Create fresh store
    store = DualVectorStore(text_dim=VECTOR_DIM, image_dim=IMAGE_VECTOR_DIM)

    # Reset indexes
    store.text_index.reset()
    store.text_id_map.clear()
    store.image_index.reset()
    store.image_id_map.clear()

    # Separate items by source
    text_items = []
    screenshot_items = []

    for item in rows:
        if item.source == "clipboard":
            text_items.append(item)
        elif item.source == "screenshot":
            screenshot_items.append(item)

    print(f"Processing {len(text_items)} clipboard items (text only)")
    print(f"Processing {len(screenshot_items)} screenshots (text + image)")

    # Process clipboard items (text vectors only)
    for start in range(0, len(text_items), batchsize):
        end = min(start + batchsize, len(text_items))
        batch = text_items[start:end]
        texts = [item.text for item in batch]

        # Encode batch
        vectors = encode_many_texts(texts)

        # Add to text index
        for item, vec in zip(batch, vectors):
            store.add_text_vector(item_id=item.id, vector=vec)

        print(f"Added text batch {start}-{end - 1} ({end - start} items)")

    # Process screenshot items (text + image vectors)
    for idx, item in enumerate(screenshot_items):
        try:
            # Add text vector from OCR
            if item.text and item.text != "[No text detected]":
                text_vector = encode_many_texts([item.text])[0]
                store.add_text_vector(item_id=item.id, vector=text_vector)

            # Add image vector from CLIP
            if item.blob_uri:
                import os
                if os.path.exists(item.blob_uri):
                    image_vector = encode_image(item.blob_uri)
                    store.add_image_vector(item_id=item.id, vector=image_vector)
                else:
                    print(f"[WARN] Image not found: {item.blob_uri}")

            if (idx + 1) % 10 == 0:
                print(f"Processed {idx + 1}/{len(screenshot_items)} screenshots")

        except Exception as e:
            print(f"[ERROR] Failed to process item #{item.id}: {e}")
            continue

    # Save indexes
    store.save()
    stats = store.get_stats()
    print("[SYSTEM] Index rebuilt and saved successfully.")
    print(f"[STATS] Text vectors: {stats['text_vectors']}, Image vectors: {stats['image_vectors']}")


def main() -> None:
    rebuild_index()


if __name__ == "__main__":
    main()