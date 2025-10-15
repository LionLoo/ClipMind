# Purpose: watch OS clipboard. Whenever text changes, save row into database
# added FAISS index in real-time
# added deduplication (exact + near dup) and junk filtering
# exact dupes are found via content_hash index
# FIXED: Uses DualVectorStore

import time
from typing import Optional
import pyperclip
from sqlmodel import select
from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.vector_store import DualVectorStore
from app.search.encoder import encode_text_to_vector, VECTOR_DIM
from app.search.clip_encoder import IMAGE_VECTOR_DIM
import xxhash


# ===== JUNK FILTERING RULES =====

def is_junk(text: str) -> bool:
    """
    Detect if clipboard text is Junk/Noise
    Returns True if it is
    """
    # Rule 1: too short (less than min_length characters)
    min_length = 5
    if len(text) < min_length:
        return True

    # Rule 2: Only whitespace
    if not text.strip():
        return True

    # Rule 3: Only repeated characters (AAAA, 1111)
    if len(set(text.strip())) == 1:
        return True

    # Rule 4: Only emojis or special characters (no alphanumeric)
    if not any(c.isalnum() for c in text):
        return True

    # Rule 5: Common boilerplate patterns
    junk_patterns = [
        "copied to clipboard",
        "copy successful",
        "ctrl+c",
        "cmd+c",
    ]
    text_lower = text.lower()
    if any(pattern in text_lower for pattern in junk_patterns):
        return True

    return False


# ===== Deduplication =====
def compute_hash(text: str) -> str:
    """Computes xxhash64 of text to find exact dedups"""
    return xxhash.xxh64(text.encode('utf-8')).hexdigest()


def check_exact_duplicate(text_hash: str) -> Optional[int]:
    """
    Check if exact dup exists in DB using indexed hash
    Returns item_id if one is found, otherwise None
    O(1) lookup with constant hash!
    """
    with get_session() as session:
        statement = select(Item).where(Item.content_hash == text_hash).limit(1)
        item = session.exec(statement).first()

        if item:
            return item.id

        return None


def check_near_duplicates(text: str, store: DualVectorStore, similarity_threshold: float = 0.95) -> Optional[tuple]:
    """
    Check if very similar item exists with FAISS

    Args:
        text: text to check
        store: DualVectorStore
        similarity_threshold: Cosine Similarity threshold (higher = more similar)

    returns:
        (item_id, similarity_score) if found else None
    """
    if store.text_index.ntotal == 0:
        return None

    vector = encode_text_to_vector(text)
    distances, positions, item_ids = store.search_text(vector, top_k=1)

    if len(item_ids) == 0 or item_ids[0] == -1:
        return None

    # Converts L2 distance to cos similarity
    distance = float(distances[0][0])
    if distance < 0.3:  # check and change later if needed
        item_id = item_ids[0]
        similarity = 1.0 - (distance / 10.0)  # converts to 0-1 scale
        return (item_id, similarity)

    return None


def read_clipboard_text():
    """Try to read text from Clipboard"""
    try:
        raw = pyperclip.paste()
    except pyperclip.PyperclipException:
        return None

    if not isinstance(raw, str):
        return None

    clean = raw.strip()
    if clean == "":
        return None

    return clean


def watch_clipboard():
    """
    Starts the Clipboard manager
    Polls every few hundred ms
    Saves to DB and indexes in FAISS
    filters our exact dups, near dups, and junk filtering
    """
    init_db()
    last_text = None
    poll_ms = 1000

    print("[SYSTEM] Loading FAISS indexes...")
    store = DualVectorStore(text_dim=VECTOR_DIM, image_dim=IMAGE_VECTOR_DIM)

    print(f"[SYSTEM] Deduplication: Exact and near detection enabled")
    save_counter = 0  # track num items since last save
    save_interval = 1  # save index to disk every N items

    # Stats counters
    total_captured = 0
    junk_filtered = 0
    exact_dupes_skipped = 0
    near_dupes_skipped = 0
    print("[SYSTEM] ClipMind Clipboard Watcher Initiated! Start Copying!")

    while True:
        current = read_clipboard_text()

        if current is not None and current != last_text:
            last_text = current
            total_captured += 1

            # Junk Filter
            if is_junk(current):
                junk_filtered += 1
                print(f"[SKIP] Junk filtered (total junk: {junk_filtered})")
                continue

            # Exact Duplicate Check Hashed lookup
            content_hash = compute_hash(current)
            existing_id = check_exact_duplicate(content_hash)

            if existing_id is not None:
                exact_dupes_skipped += 1
                print(f"[SKIP] Exact duplicate of Item #{existing_id} (total exact dupes: {exact_dupes_skipped})")
                continue

            # Near Duplicate Check
            near_dupe = check_near_duplicates(current, store, similarity_threshold=0.95)

            if near_dupe is not None:
                dupe_id, similarity = near_dupe
                near_dupes_skipped += 1
                print(
                    f"[SKIP] Near-duplicate of Item #{dupe_id} (similarity: {similarity:.2%}, total near dupes: {near_dupes_skipped})")
                continue

            # insert into DB
            with get_session() as session:
                new_item = Item(
                    text=current,
                    content_hash=content_hash,
                    source="clipboard",  # mark as from clipboard
                    blob_uri=None  # no image for clipboard
                )
                session.add(new_item)
                session.commit()
                session.refresh(new_item)

            # Encode text to vector
            try:
                vector = encode_text_to_vector(current)
                store.add_text_vector(item_id=new_item.id, vector=vector)
                save_counter += 1

                if save_counter >= save_interval:
                    store.save()
                    print(f"[SYSTEM] Index saved to disk ({store.text_index.ntotal} text vectors)")
                    save_counter = 0
            except Exception as e:
                print(f"[ERROR] Failed to index item #{new_item.id}: {e}")

            # Display confirmation
            if len(current) > 80:
                shortened_text = current[:80] + "..."
            else:
                shortened_text = current

            print("[ITEM] Saved Item #" + str(new_item.id) + " | " + repr(shortened_text))

            # Show stats every 10 items
            if total_captured % 10 == 0:
                saved = total_captured - junk_filtered - exact_dupes_skipped - near_dupes_skipped
                print(
                    f"[STATS] Captured: {total_captured} | Saved: {saved} | Junk: {junk_filtered} | Exact dupes: {exact_dupes_skipped} | Near dupes: {near_dupes_skipped}")

        time.sleep(poll_ms / 1000.0)


def main():
    watch_clipboard()


if __name__ == "__main__":
    main()