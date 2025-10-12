from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Index


class Item(SQLModel, table=True):
    """Defines the Schema of the table"""

    __table_args__ = (
        Index('ix_item_content_hash', 'content_hash'),  # Index for fast duplicate lookups
        Index('ix_item_source', 'source'),  # Index for filtering by source type
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    text: str  # OCR text for screenshots, clipboard text for clipboard items

    content_hash: str = Field(index=True)  # xxhash64 for exact deduplication

    source: str = Field(default="clipboard", index=True)  # "clipboard" or "screenshot"

    blob_uri: Optional[str] = Field(default=None)  # Path to image file for screenshots, None for clipboard

    created_ts: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    readable_time: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
