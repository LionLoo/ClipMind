# Purpose: Migrate existing database to add content_hash field to all items
# Run this AFTER updating models.py with the new schema

import xxhash
import sqlite3
from sqlmodel import select

from app.db.session import get_session
from app.db.models import Item
from app.core import config


def compute_hash(text: str) -> str:
    """Compute xxhash64 of text"""
    return xxhash.xxh64(text.encode('utf-8')).hexdigest()


def migrate():
    """
    Add content_hash column to existing items table and populate it
    """
    print("[MIGRATION] Starting migration to add content_hash...")

    # Extract database path from sqlite_url
    # Format: "sqlite:///clipmind.db"
    db_path = config.sqlite_url.replace("sqlite:///", "")

    # Connect directly to SQLite to add the column
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if content_hash column already exists
    cursor.execute("PRAGMA table_info(item)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'content_hash' not in columns:
        print("[MIGRATION] Adding content_hash column to item table...")
        try:
            cursor.execute("ALTER TABLE item ADD COLUMN content_hash VARCHAR")
            conn.commit()
            print("[MIGRATION] Column added successfully!")
        except sqlite3.OperationalError as e:
            print(f"[ERROR] Could not add column: {e}")
            conn.close()
            return
    else:
        print("[MIGRATION] content_hash column already exists.")

    # Create index on content_hash for fast lookups
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_item_content_hash ON item (content_hash)")
        conn.commit()
        print("[MIGRATION] Index created on content_hash column.")
    except sqlite3.OperationalError as e:
        print(f"[WARN] Could not create index: {e}")

    conn.close()

    # Now populate the content_hash for all existing items using SQLModel
    print("[MIGRATION] Populating content_hash for existing items...")

    with get_session() as session:
        # Get all items
        statement = select(Item)
        items = session.exec(statement).all()

        if not items:
            print("[MIGRATION] No items found in database. Nothing to migrate.")
            return

        print(f"[MIGRATION] Found {len(items)} items to migrate...")

        # Update each item with its content_hash
        migrated = 0
        for item in items:
            # Check if content_hash is missing or empty
            if not item.content_hash or item.content_hash == "":
                item.content_hash = compute_hash(item.text)
                migrated += 1

                if migrated % 100 == 0:
                    print(f"[MIGRATION] Processed {migrated}/{len(items)} items...")

        # Commit all changes
        session.commit()

        print(f"[MIGRATION] Successfully migrated {migrated} items!")
        print(f"[MIGRATION] Migration complete. Database is ready.")


if __name__ == "__main__":
    migrate()