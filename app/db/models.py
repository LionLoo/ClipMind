from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

class Item(SQLModel, table=True):
    """Defines the Schema of the table"""

    id: Optional[int] = Field(default=None, primary_key=True)

    text: str

    created_ts: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    readable_time: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )