# 🧠 ClipMind / MemoryMesh

> A local-first “second brain” for your clipboard and screenshots.  
> Built to capture everything you copy, make sense of it, and let you recall it instantly — semantically, not just by keywords.

---

### 🚧 Work in Progress
This project is **actively being built**.  
Things will definitely change, break, and get rewritten. I’m still wiring together the backend (FAISS, SQLModel, encoder) and designing the GUI.

---

### 💡 What It Does (so far)
- Watches your **clipboard** in real time and saves anything you copy into a local database.
- Encodes each clipboard entry into an embedding vector using a text encoder (Sentence-Transformers / CLIP).
- Adds those vectors into a **FAISS** index so you can perform fast semantic searches.
- Exposes a simple **FastAPI** server for:
  - `/search` → find items by meaning  
  - `/item/{id}` → retrieve a specific saved item  
  - `/items/recent` → list your recent copies  
  - `/stats` → view total items, index size, and vector dimension

Everything runs locally — no cloud dependency.

---

### 🏗️ Stack
| Layer | Tools |
|:--|:--|
| Database | SQLite + SQLModel |
| Vector Store | FAISS (persistent on disk) |
| Encoder | Sentence-Transformers / CLIP-style embeddings |
| API | FastAPI (async, typed, documented) |
| Utilities | Pyperclip for clipboard capture |
| Language | Python 3.10+ |

---

### 🚀 Running It Locally

## TODO
