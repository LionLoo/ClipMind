import pyperclip
import time
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from tinydb.middlewares import CachingMiddleware
from datetime import datetime
from sentence_transformers import SentenceTransformer
import config
import json

db = TinyDB(
    config.db_file,
    storage=CachingMiddleware(
        lambda path: JSONStorage(path, indent=4, separators=(",", ": ")),
    )
)
embedded_model = SentenceTransformer(config.embedded_model_name)
existing_texts = set(entry["text"] for entry in db.all())

last_copy = ""

print("👀 ClipMind is Always Watching")
while True:
    try:
        time.sleep(3)

        current_copy = pyperclip.paste()
        if (current_copy != last_copy):
            if current_copy in existing_texts:
                db.update({
                    "timestamp": time.time(),
                    "readable_time": datetime.now().strftime('%Y-%m-%d: %H:%M:%S'),
                }, Query().text == current_copy)
                print(f"[+] updated: {current_copy}")

            else:
                embedding = embedded_model.encode(current_copy).tolist()
                entry = {
                    "text": current_copy,
                    "timestamp": time.time(),
                    "readable_time": datetime.now().strftime('%Y-%m-%d: %H:%M:%S'),
                    "image_path": None, #TODO allow for images
                    "embedding": embedding
                }
                db.insert(entry)
                db.storage.flush()
                existing_texts.add(current_copy)
                print(f"[+] saved: {current_copy} \n Embedding: {embedding[:5]}")

            last_copy = current_copy


    except KeyboardInterrupt:
        print("💤 ClipMind has Fallen Asleep")
        db.close()