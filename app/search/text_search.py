#Purpose: search through saved clipboard items by contains() filter
import sys
from sqlmodel import select
from app.db.session import get_session, init_db
from app.db.models import Item

def search_items(query_text: str, limit: int = 10):
    """return up to 'limit' items with text that contains 'query_text'"""
    init_db()
    with get_session() as session:
        statement = select(Item).where(Item.text.contains(query_text)).limit(limit)
        results = session.exec(statement).all()
        return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.search.text_search <query> [limit]")
        sys.exit(1)

    query_text = sys.argv[1]
    if len(sys.argv) >= 3:
        raw_limit = sys.argv[2]
        try:
            limit = int(raw_limit)
        except ValueError:
            print("[WARN] Invalid limit, using 10")
            limit = 10
    else:
        limit = 10

    if limit < 1:
        print("[WARN] Limit must be >= 1. Using 1.")
        limit = 1
    elif limit > 1000:
        print("[WARN] Limit too large. Capping at 1000.")
        limit = 1000

    rows = search_items(query_text, limit)

    if not rows:
        print("[RESULT] No matches.")
        return

    print(f"Found {len(rows)} match(es) for {query_text!r}:")
    for row in rows:
        if len(row.text) > 80:
            preview = row.text[:80] + "..."
        else:
            preview = row.text

    print(
        "- #" + str(row.id)
        + " @ " + row.readable_time
        + " | " + repr(preview)
    )

if __name__ == "__main__":
    main()
