#Purpose:
#   loads SentenceTransformer model once and give functions
#   encode text into float32 vectors
# KEYNOTE:
# size of ""all-MiniLM-L6-v2"" vector is 384
# MUST UPDATE VECTOR_DIM to match if we change the model

from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from app.core import config

#vector size for chosen model
VECTOR_DIM: int = 384

_model = SentenceTransformer(config.embedded_model_name)

def encode_text_to_vector(text: str):
    """
    convert single piece of text into 1D numpy array length VECTOR_DIM
    dtype float32 (FAISS expects float32)
    """
    vector_2d = _model.encode(text)
    vector_1d = np.array(vector_2d, dtype=np.float32).reshape(-1)  # force to 1D float32
    return vector_1d

def encode_many_texts(texts: list[str]):
    """convert a list instead of just one"""
    vectors = _model.encode(texts)  #returns (N, VECTOR_DIM) so we dont have to reshape
    vectors = np.array(vectors, dtype=np.float32)
    return vectors