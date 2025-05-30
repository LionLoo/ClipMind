from tinydb import TinyDB
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

import config

db = TinyDB(config.db_file)
embedding_model = SentenceTransformer(config.embedded_model_name)

entries = db.all()

texts = []
embeddings = []

#filter out legacy entries that dont have embeddings
for entry in entries:
    if "embedding" in entry:
        texts.append(entry["text"])
        embeddings.append(entry["embedding"])

embedding_matrix = np.array(embeddings).astype("float32")

#building FAISS index
dimension = embedding_matrix.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embedding_matrix)

while True:
    try:
        query = input("\nEntry your search: ")
        query_vectory = embedding_model.encode(query).astype("float32").reshape(1,-1)

        distances, indicies = index.search(query_vectory, config.top_k_results)

        print(f"\n Top {config.top_k_results} Matches: \n ")
        for i, dist in zip(indicies[0], distances[0]):
            print(f"[{dist:.2f}] {texts[i]}")
    except KeyboardInterrupt:
        print("Goodbye :)")
