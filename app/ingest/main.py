#Purpose: watch OS clipboard. Whenever text changes, save row into database
import time
from typing import Optional
import pyperclip

from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.store import IndexStore
from app.search.encoder import encode_text_to_vector, VECTOR_DIM

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

def main():
    """
    Starts the Clipboard manager
    Polls every few hundred ms
    """

    init_db()
    last_text = None
    poll_ms = 1000

    print("[SYSTEM] Loaddings FAISS index...")
    store = IndexStore(vector_dimension=VECTOR_DIM)
    print(f"[SYSTEM] Index loaded. Current size: {store.index.ntotal} vectors")
    save_counter = 0 #track num items since last save
    save_interval = 1 #save index to disk every N items
    print("[SYSTEM] ClipMind Initiated! Start Copying!")

    while True:
        current = read_clipboard_text()

        if current is not None and current != last_text:
            last_text = current

            #insert into DB
            with get_session() as session:
                new_item = Item(text=current)
                session.add(new_item)
                session.commit()
                session.refresh(new_item)

            #Encode text to vector
            try:
                vector = encode_text_to_vector(current)

                store.add_vector(item_id=new_item.id, vector=vector)
                save_counter += 1

                if save_counter >= save_interval:
                    store.save()
                    print(f"[SYSTEM] Index saved to disk ({store.index.ntotal} vectors)")
                    save_counter = 0
            except Exception as e:
                print(f"[ERROR] Failed to index item #{new_item.id}: {e}")

            #Display confirmation
            if len(current > 80):
                shortened_text = current[:80] + "..."
            else:
                shortened_text = current

            print("[ITEM] Saved Item #" + str(new_item.id) + " | " + repr(shortened_text))

        time.sleep(poll_ms / 1000.0)

if __name__ == "__main__":
    main()






