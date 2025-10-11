import os
from sqlmodel import SQLModel, create_engine, Session
from app.core import config

def ensure_folders_exist():
    #checks FAISS files
    faiss_dir = os.path.dirname(config.faiss_index_path)
    if faiss_dir and not os.path.exists(faiss_dir):
        os.makedirs(faiss_dir, exist_ok=True)

def build_engine():
    #create the SQLAlchemy to work with SQLite
    return create_engine(config.sqlite_url, echo=False)

engine = build_engine()

def init_db():
    """create tables in db on startup"""
    ensure_folders_exist()
    SQLModel.metadata.create_all(engine)

def get_session():
    """Open DB and return it"""
    return Session(engine)

