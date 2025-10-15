# Purpose: FastAPI for ClipMind
# HTTP endpoints for search, item retrieval, and stats
# Supports: filtering by source (clipboard/screenshot), image search

from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from app.db.session import init_db, get_session
from app.db.models import Item
from app.search.semantic_search import (
    semantic_search,
    search_images_only,
    search_clipboard_only,
    search_text_only
)
from app.index.vector_store import DualVectorStore
from app.search.encoder import VECTOR_DIM
from app.search.clip_encoder import IMAGE_VECTOR_DIM
from app.core import config

app = FastAPI(
    title="ClipMind API",
    description="Second Brain for Clipboard and Screenshot Management",
    version="0.2.0"
)


# Response Models
class ItemResponse(BaseModel):
    id: int
    text: str
    source: str
    blob_uri: Optional[str]
    created_ts: int
    readable_time: str

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    id: int
    text: str
    source: str
    blob_uri: Optional[str]
    created_ts: int
    readable_time: str
    score: float
    preview: str


class SearchResponse(BaseModel):
    query: str
    mode: str
    results: List[SearchResult]
    count: int


class StatsResponse(BaseModel):
    total_items: int
    clipboard_items: int
    screenshot_items: int
    text_vectors: int
    image_vectors: int
    text_vector_dim: int
    image_vector_dim: int


# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    print("[API] ClipMind API server started")


# === ENDPOINTS ===
@app.on_event("startup")
async def startup_event():
    init_db()
    print("[API] ClipMind API server started")
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "ClipMind API",
        "status": "running",
        "version": "0.2.0"
    }


@app.get("/search", response_model=SearchResponse)
async def search(
        q: str = Query(..., description="Search query text"),
        k: int = Query(default=None, description=f"Number of results (default: {config.top_k_results})", ge=1, le=100),
        mode: str = Query(default="all", description="Search mode: all, text, images, clipboard"),
        after: int = Query(default=None, description="Only return items after this timestamp")
):

    """
       Semantic search through clipboard and screenshot history

       - q: Search query text
       - k: Number of results to return
       - mode: Search mode
         - "all": Search everything (default)
         - "text": Search text content only (clipboard + OCR)
         - "images": Search screenshot images by visual content
         - "clipboard": Search clipboard items only
       """

    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' cannot be empty")

    top_k = k if k is not None else config.top_k_results

    try:
        # Route to appropriate search function WITH time filter
        if mode == "images":
            results = search_images_only(q.strip(), top_k=top_k, after_timestamp=after)
        elif mode == "clipboard":
            results = search_clipboard_only(q.strip(), top_k=top_k, after_timestamp=after)
        elif mode == "text":
            results = search_text_only(q.strip(), top_k=top_k, after_timestamp=after)
        else:
            results = semantic_search(q.strip(), top_k=top_k, mode="all", after_timestamp=after)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    # Format results
    search_results = []
    for item, distance in results:
        preview = item.text[:80] + "..." if len(item.text) > 80 else item.text
        search_results.append(SearchResult(
            id=item.id,
            text=item.text,
            source=item.source,
            blob_uri=item.blob_uri,
            created_ts=item.created_ts,
            readable_time=item.readable_time,
            score=distance,
            preview=preview
        ))

    return SearchResponse(
        query=q,
        mode=mode,
        results=search_results,
        count=len(search_results)
    )


@app.get("/item/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int):
    """
    Get a specific item by ID
    """
    with get_session() as session:
        statement = select(Item).where(Item.id == item_id)
        item = session.exec(statement).first()

        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

        return ItemResponse.model_validate(item)


@app.get("/item/{item_id}/image")
async def get_item_image(item_id: int):
    """
    Get the screenshot image file for an item
    Returns 404 if item is not a screenshot or file doesn't exist
    """
    with get_session() as session:
        statement = select(Item).where(Item.id == item_id)
        item = session.exec(statement).first()

        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

        if item.source != "screenshot" or not item.blob_uri:
            raise HTTPException(status_code=404, detail=f"Item {item_id} is not a screenshot")

        import os
        if not os.path.exists(item.blob_uri):
            raise HTTPException(status_code=404, detail=f"Image file not found: {item.blob_uri}")

        return FileResponse(item.blob_uri)


@app.get("/items/recent")
async def get_recent_items(
        limit: int = Query(default=20, ge=1, le=100),
        source: Optional[str] = Query(default=None, description="Filter by source: clipboard or screenshot")
):
    """
    Get most recent items

    - limit: Number of items to return
    - source: Optional filter by source type
    """
    with get_session() as session:
        statement = select(Item).order_by(Item.created_ts.desc())

        if source:
            statement = statement.where(Item.source == source)

        statement = statement.limit(limit)
        items = session.exec(statement).all()

        return {
            "count": len(items),
            "source_filter": source,
            "items": [ItemResponse.model_validate(item) for item in items]
        }


@app.get("/items/screenshots")
async def get_screenshots(limit: int = Query(default=20, ge=1, le=100)):
    """
    Get recent screenshots only
    """
    return await get_recent_items(limit=limit, source="screenshot")


@app.get("/items/clipboard")
async def get_clipboard_items(limit: int = Query(default=20, ge=1, le=100)):
    """
    Get recent clipboard items only
    """
    return await get_recent_items(limit=limit, source="clipboard")


@app.delete("/item/{item_id}")
async def delete_item(item_id: int):
    """
    Delete an item by ID

    Note: This only deletes from the database.
    FAISS index cleanup requires rebuild.
    """
    with get_session() as session:
        statement = select(Item).where(Item.id == item_id)
        item = session.exec(statement).first()

        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

        session.delete(item)
        session.commit()

        return {"status": "deleted", "id": item_id}


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get system statistics
    """
    with get_session() as session:
        # Total items
        total_items = len(session.exec(select(Item)).all())

        # Count by source
        clipboard_items = len(session.exec(
            select(Item).where(Item.source == "clipboard")
        ).all())

        screenshot_items = len(session.exec(
            select(Item).where(Item.source == "screenshot")
        ).all())

    # Get vector index stats
    try:
        store = DualVectorStore(text_dim=VECTOR_DIM, image_dim=IMAGE_VECTOR_DIM)
        text_vectors = store.text_index.ntotal
        image_vectors = store.image_index.ntotal
    except Exception as e:
        print(f"[WARN] Could not load vector indexes: {e}")
        text_vectors = 0
        image_vectors = 0

    return StatsResponse(
        total_items=total_items,
        clipboard_items=clipboard_items,
        screenshot_items=screenshot_items,
        text_vectors=text_vectors,
        image_vectors=image_vectors,
        text_vector_dim=VECTOR_DIM,
        image_vector_dim=IMAGE_VECTOR_DIM
    )


# CORS middleware
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)