from sentence_transformers import SentenceTransformer
import numpy as np
from app.core import config

embedding_model = SentenceTransformer(config.embedded_model_name)

def encode_query(text: str) -> np.ndarray:
    return embedding_model.encode(text).astype("float32").reshape(1, -1)
