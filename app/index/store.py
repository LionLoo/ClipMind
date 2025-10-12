#ARCHIVED FOR WHEN JUST TEXT -> MOVED TO VECTOR_STORE (HANDLES BOTH TEXT AND IMAGES)
#purpose:
#keep persistent FAISS index in DISK
# -add one vector per saved ITEM (row in DB)
# -search for nearest neighbors by meaning (vector similarity)
# -save and load the index for next restart

#writes to files:
# -config.faiss_index_path --> "faiss/clipmind.index"
# -config.faiss_idmap_path --> "faiss.idmap.npy"

#Rules:
# -id_map[position] == item_id stored at the FAISS position

import os
from typing import List, Tuple

import numpy as np
import faiss

from app.core import config

class IndexStore:
    def __init__(self, vector_dimension: int):
        """
        Makes sure we have index in memory and ID map in memeory
        Loads disk files if they exist elsewise creates it
        """
        self.vector_dimension = int(vector_dimension)
        self.index_path = config.faiss_index_path
        self.idmap_path = config.faiss_idmap_path

        index_folder = os.path.dirname(self.index_path)
        if index_folder and not os.path.exists(index_folder):
            os.makedirs(index_folder, exist_ok=True)

        self.index = None #FAISS index obj
        self.id_map: List[int] = [] #Python list map "FAISS pos --> item.id"

        self._load_from_disk_or_start_fresh()

    def _load_from_disk_or_start_fresh(self):
        """
        if files are present, load
        else create empty index and empty id_map
        """

        index_exists = os.path.exists(self.index_path)
        idmap_exists = os.path.exists(self.idmap_path)

        #load existing data if they exist
        if index_exists and idmap_exists:
            self.index = faiss.read_index(self.index_path)
            loaded_ids = np.load(self.idmap_path)
            self.id_map = [int(x) for x in loaded_ids.tolist()]

            #checks to make sure vector dimentions match what we expect


            if int(self.index.d) != self.vector_dimension:
                raise ValueError(
                    "FAISS index dimension on disk is "
                    + str(self.index.d)
                    + " but we expected "
                    + str(self.vector_dimension)
                    + "."
                )
        else:
            #create them with flat and L2 (euclidean distance)
            self.index = faiss.IndexFlatL2(self.vector_dimension)
            self.id_map = []

    def add_vector(self, item_id: int, vector: np.ndarray):
        """
        Adds 1 vector for an item
        -item_id: database primary key (Item.id)
        -vector: 1d array or 2d array of float32
        """
        if vector is None:
            raise ValueError("[ERROR] Vector is None. cannot add to index")

        #force to be 2D (1, dim)
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)

        #ensure float32
        if vector.dtype != np.float32:
            vector = vector.astype("float32")

        self.index.add(vector) #add to the FAISS index
        self.id_map.append(int(item_id)) #track which DB row this vector belongs to

    def search(self, query_vector: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """
        Finds top_k nearest neighbors to query_vector
        return values:
            - distances
            - positions (positions inside FAISS)
            - item_ids: list[int] mapped from positions to actually DB row ids
        """
        #forces input to (1,dim) and float32
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        if query_vector.dtype != np.float32:
            query_vector = query_vector.astype("float32")

        distances, positions = self.index.search(query_vector, int(top_k))

        #find the DB item ids from the FAISS positions
        item_ids = []
        for pos in positions[0]:
            if 0 <= pos < len(self.id_map):
                item_ids.append(self.id_map[pos])
            else:
                item_ids.append(-1) #no valid id for current slot

        return distances, positions, item_ids

    def save(self):
        """
        Writes FAISS index and id_map to disk
        CALL AFTER BATCHES OF ADS
        """
        faiss.write_index(self.index, self.index_path)
        np.save(self.idmap_path, np.array(self.id_map, dtype=np.int64))
