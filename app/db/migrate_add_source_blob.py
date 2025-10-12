# Purpose: Migrate database to add source and blob_uri columns
# Run this AFTER updating models.py

import sqlite3
from app.core import config


def migrate():
    """Add source and blob_uri columns to existing items table"""

    print("[MIGRATION] Starting migration to add source and blob_uri...")

    db_path = config.sqlite_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(item)")
    columns = [column[1] for column in cursor.fetchall()]

    # Add source column if missing
    if 'source' not in columns:
        print("[MIGRATION] Adding source column...")
        try:
            cursor.execute("ALTER TABLE item ADD COLUMN source VARCHAR DEFAULT 'clipboard'")
            conn.commit()
            print("[MIGRATION] source column added!")
        except sqlite3.OperationalError as e:
            print(f"[ERROR] Could not add source column: {e}")
    else:
        print("[MIGRATION] source column already exists.")

    # Add blob_uri column if missing
    if 'blob_uri' not in columns:
        print("[MIGRATION] Adding blob_uri column...")
        try:
            cursor.execute("ALTER TABLE item ADD COLUMN blob_uri VARCHAR")
            conn.commit()
            print("[MIGRATION] blob_uri column added!")
        except sqlite3.OperationalError as e:
            print(f"[ERROR] Could not add blob_uri column: {e}")
    else:
        print("[MIGRATION] blob_uri column already exists.")

    # Create index on source for fast filtering
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_item_source ON item (source)")
        conn.commit()
        print("[MIGRATION] Index created on source column.")
    except sqlite3.OperationalError as e:
        print(f"[WARN] Could not create index: {e}")

    # Update existing items to have source='clipboard' if NULL
    cursor.execute("UPDATE item SET source = 'clipboard' WHERE source IS NULL")
    conn.commit()

    conn.close()

    print("[MIGRATION] Migration complete! Database is ready.")


if __name__ == "__main__":
    migrate()
