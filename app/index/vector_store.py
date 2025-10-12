#Purpose:
#Migrated from store.py
#Manages seperate FAISS indexes for text and image embeddings
#text vectors: from OCR/Clipboard text (384d from sentencetransformers)
#image vectors: from CLIP image understanding (512d from CLIP)


import os
from typing import List, Tuple, Literal
import numpy as np
import faiss
from app.core import config

VectorKind = Literal["text", "image"]

class DualVectorStore:
    """
    Manages seperate FAISS Indexes
    - text_index: for text embeddings
    - image_index for CLIP image embeddings
    """

    def __init__(self, text_dim: int = 384, image_dim: int = 512):
        self.text_dim = text_dim
        self.image_dim = image_dim

        # Paths
        self.text_index_path = "faiss/text_vectors.index"
        self.text_idmap_path = "faiss/text_idmap.npy"
        self.image_index_path = "faiss/image_vectors.index"
        self.image_idmap_path = "faiss/image_idmap.npy"

        # Ensure faiss directory exists
        os.makedirs("faiss", exist_ok=True)

        # Initialize indexes
        self.text_index = None
        self.text_id_map: List[int] = []
        self.image_index = None
        self.image_id_map: List[int] = []

        self._load_or_create_indexes()

    def _load_or_create_indexes(self):
        """Loads imdexes from Disk or create fresh ones"""
        # Text index
        if os.path.exists(self.text_index_path) and os.path.exists(self.text_idmap_path):
            self.text_index = faiss.read_index(self.text_index_path)
            self.text_id_map = np.load(self.text_idmap_path).tolist()
        else:
            self.text_index = faiss.IndexFlatL2(self.text_dim)
            self.text_id_map = []

        # Image index
        if os.path.exists(self.image_index_path) and os.path.exists(self.image_idmap_path):
            self.image_index = faiss.read_index(self.image_index_path)
            self.image_id_map = np.load(self.image_idmap_path).tolist()
        else:
            self.image_index = faiss.IndexFlatL2(self.image_dim)
            self.image_id_map = []

    def add_text_vector(self, item_id: int, vector: np.ndarray):
        """Add a text vector (from clipboard or OCR)"""

        # force to be 2D (1, dim) and float32
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        if vector.dtype != np.float32:
            vector = vector.astype("float32")

        self.text_index.add(vector)
        self.text_id_map.append(int(item_id))

    def add_image_vector(self, item_id: int, vector: np.ndarray):
        """Add an image vector (from CLIP)"""

        # force to be 2D (1, dim) and float32
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        if vector.dtype != np.float32:
            vector = vector.astype("float32")

        self.image_index.add(vector)
        self.image_id_map.append(int(item_id))

    def search_text(self, query_vector: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """Search in text vectors"""
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        if query_vector.dtype != np.float32:
            query_vector = query_vector.astype("float32")

        distances, positions = self.text_index.search(query_vector, top_k)

        item_ids = []

        # find the DB item ids from the FAISS positions
        for pos in positions[0]:
            if 0 <= pos < len(self.text_id_map):
                item_ids.append(self.text_id_map[pos])
            else:
                item_ids.append(-1) #no valid result, return -1

        return distances, positions, item_ids

    def save(self):
        """
        Writes FAISS index and id_map to disk
        CALL AFTER BATCHES OF ADDS
        """

        #save the text index
        faiss.write_index(self.text_index, self.text_index_path)
        np.save(self.text_idmap_path, np.array(self.text_id_map, dtype=np.int64))

        #save the image index
        faiss.write_index(self.image_index, self.image_index_path)
        np.save(self.image_idmap_path, np.array(self.image_id_map, dtype=np.int64))

    def get_stats(self):
        """Get statistics about the indexes"""
        return {
            "text_vectors": self.text_index.ntotal,
            "image_vectors": self.image_index.ntotal,
            "total_items": len(set(self.text_id_map + self.image_id_map))
        }
