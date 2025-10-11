#Purpose:
# Read all saved items from DB, turn text into vectors
# add vectors to FAISS index, save the index to disk
#Notes:
# only need to run first time we want to use semantic search
# run anyuthing we change the embedding model to rebuild cleanly
#How to run:
# python -m app.index.rebuild_from_db

from typing import List
from sqlmodel import select

from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.store import IndexStore
from app.search.encoder import encode_many_texts, VECTOR_DIM

def read_all_items_texts() -> List[Item]:
    """Load all items from DB and return list of items"""

    init_db()
    with get_session() as session:
        statement = select(Item).order_by(Item.id.asc())
        rows: List[Item] = session.exec(statement).all()
        return rows

def rebuild_index(batchsize: int = 1024):
    """
    build fresh FAISS index from every row in DB
    WARNING: replaces whatever was there before
    """

    #load rows from DB
    rows = read_all_items_texts()
    if not rows:
        print("No rows found in DB")
        return
    total = len(rows)
    print("Found", len(rows), f"row(s). Encoding into vectors with batchsize={batchsize}")
    store = IndexStore(vector_dimension=VECTOR_DIM)
    store.index.reset()
    store.id_map.clear()

    #process batches: encode -> add to FAISS -> update id_map
    for start in range(0, total, batchsize):
        end = min(start + batchsize, total)
        batch_rows = rows[start:end]
        texts = [r.text for r in batch_rows]

        #encode batch -> (B, VECTOR_DIM)
        vectors_2d = encode_many_texts(texts)
        if vectors_2d.ndim != 2 or vectors_2d.shape[1] != VECTOR_DIM:
            raise ValueError(f"Bad vector shape {vectors_2d.shape}; expected (B, {VECTOR_DIM}).")

        #add vector + db id
        for r, vec in zip(batch_rows, vectors_2d):
            store.add_vector(item_id=r.id, vector=vec)

        print(f"Added batch {start}-{end - 1} ({end - start} items)")

    store.save()
    print("[SYSTEM] Index rebuilt and saved successfully.")


def main() -> None:
    rebuild_index()


if __name__ == "__main__":
    main()