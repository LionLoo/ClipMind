# Purpose: watch screenshot folder, extract text with OCR and understand images with CLIP
# stores path to original screenshot + dual embeddings
# does not store the image again, references the existing files
# added persistent tracking! (remembers which files are processed across restarts)
# FIXED: Auto-detects OneDrive Pictures folder

import time
import os
from pathlib import Path
from typing import Optional, Set
import xxhash
from PIL import Image
import json
from sqlmodel import select
from app.db.session import init_db, get_session
from app.db.models import Item
from app.index.vector_store import DualVectorStore
from app.search.encoder import encode_text_to_vector, VECTOR_DIM
from app.search.clip_encoder import encode_image, IMAGE_VECTOR_DIM
from app.core.config import PROCESSED_CACHE_FILE


# Auto-detect screenshot folder (checks OneDrive first, then local)
def get_screenshot_folder():
    """Find the Screenshots folder - checks OneDrive first"""
    # Check OneDrive Pictures
    onedrive_pictures = os.path.join(os.path.expanduser("~"), "OneDrive", "Pictures")
    if os.path.exists(onedrive_pictures):
        return onedrive_pictures

    # Fallback to local Pictures
    local_pictures = os.path.join(os.path.expanduser("~"), "Pictures")
    if os.path.exists(local_pictures):
        return local_pictures

    # Last resort - just Pictures
    return os.path.join(os.path.expanduser("~"), "Pictures")


DEFAULT_SCREENSHOT_FOLDER = get_screenshot_folder()

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}

# === OCR EXTRACTION ===

# Initialize EasyOCR reader (lazy loading)
_ocr_reader = None


def get_ocr_reader():
    """Lazy load EasyOCR reader"""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            print("[SYSTEM] Loading EasyOCR (first time only)...")
            _ocr_reader = easyocr.Reader(['en'], gpu=False)  # English only, CPU mode
            print("[SYSTEM] EasyOCR loaded successfully")
        except ImportError:
            print("[WARN] EasyOCR not installed. Install with: pip install easyocr")
            _ocr_reader = False
        except Exception as e:
            print(f"[WARN] EasyOCR failed to load: {e}")
            _ocr_reader = False
    return _ocr_reader


def extract_text_from_image(image_path: str) -> Optional[str]:
    """Extract text from image using EasyOCR"""
    reader = get_ocr_reader()

    if reader is False:
        # OCR not available
        return "[No text detected - OCR unavailable]"

    try:
        # EasyOCR returns list of (bbox, text, confidence)
        results = reader.readtext(image_path)

        # Combine all detected text
        text_parts = [result[1] for result in results]
        text = " ".join(text_parts).strip()

        return text if text else "[No text detected]"

    except Exception as e:
        print(f"[WARN] OCR failed for {os.path.basename(image_path)}: {e}")
        return "[No text detected]"


# === DEDUPLICATION ===
#unsued, realized ocr hash isnt good for checking dedups of images
def compute_hash(text: str) -> str:
    """Compute xxhash64 of text"""
    return xxhash.xxh64(text.encode('utf-8')).hexdigest()


def check_exact_duplicate(text_hash: str) -> Optional[int]:
    """Check if exact duplicate exists in database"""
    with get_session() as session:
        statement = select(Item).where(Item.content_hash == text_hash).limit(1)
        item = session.exec(statement).first()

        if item:
            return item.id

    return None


def is_junk_text(text: str) -> bool:
    """Check if OCR text is junk (more lenient since the image itself is more important)"""
    if text == "[No text detected]":
        return False

    if len(text) < 3:
        return True

    return False

def compute_image_hash(file_path: str) -> str:
    hasher = xxhash.xxh64()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()



# === FILE TRACKING ===

class ProcessedFilesTracker:
    """
    Track which files we've already processed
    Saved to disk so we remember across restarts
    """

    def __init__(self, cache_file: str = PROCESSED_CACHE_FILE):
        self.cache_file = cache_file
        self.processed: Set[str] = self._load_cache()
        self.save_counter = 0
        self.save_interval = 1  # Save cache every N new files

    def _load_cache(self) -> Set[str]:
        """Load processed files list from disk"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    print(f"[CACHE] Loaded {len(data)} previously processed files")
                    return set(data)
            except Exception as e:
                print(f"[WARN] Could not load cache: {e}")
                return set()
        return set()

    def _save_cache(self):
        """Save processed files list to disk"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(list(self.processed), f)
        except Exception as e:
            print(f"[ERROR] Could not save cache: {e}")

    def is_processed(self, file_path: str) -> bool:
        """Check if file has been processed"""
        return file_path in self.processed

    def mark_processed(self, file_path: str):
        """Mark file as processed and periodically save to disk"""
        self.processed.add(file_path)
        self.save_counter += 1

        # Save cache periodically
        if self.save_counter >= self.save_interval:
            self._save_cache()
            self.save_counter = 0

    def force_save(self):
        """Force save cache to disk (call on shutdown)"""
        self._save_cache()


# === MAIN WATCHER ===
def watch_screenshots(folder_path: str = None, poll_seconds: int = 5):
    """
    Watch folder for new screenshot files and process
    Stores: path to screenshot + OCR text + CLIP image embedding
    """
    if folder_path is None:
        folder_path = DEFAULT_SCREENSHOT_FOLDER

    folder = Path(folder_path)
    if not folder.exists():
        print(f"[ERROR] Screenshot folder does not exist: {folder_path}")
        print(f"[INFO] Please create the folder or specify a different path")
        return
    startup_time = time.time()
    print(f"[SYSTEM] Ignoring screenshots created before {time.ctime(startup_time)}")

    print(f"[SYSTEM] Watching folder: {folder_path}")
    init_db()
    store = DualVectorStore(text_dim=VECTOR_DIM, image_dim=IMAGE_VECTOR_DIM)
    tracker = ProcessedFilesTracker()

    # Mark existing files as processed so we don't run OCR/CLIP on old screenshots
    print("[SYSTEM] Scanning for existing files...")
    # existing_count = 0
    # for file_path in folder.glob("**/*"):  # Searches all directories recursively
    #     if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
    #         if not tracker.is_processed(str(file_path)):
    #             tracker.mark_processed(str(file_path))
    #             existing_count += 1
    #
    # if existing_count > 0:
    #     print(f"[SYSTEM] Marked {existing_count} existing files as processed (won't re-process old screenshots)")
    #     tracker.force_save()
    # NEW: Only index screenshots created AFTER this moment



    print(f"[SYSTEM] Tracking {len(tracker.processed)} total files")
    print("[SYSTEM] Screenshot watcher started! Take screenshots to capture them.")
    print("=" * 60)

    save_counter = 0
    save_interval = 5

    total_screenshots = 0
    ocr_success = 0
    ocr_failed = 0
    duplicates_skipped = 0

    try:
        while True:
            # Scan folder for new images
            for file_path in folder.glob("**/*"):
                if not file_path.is_file() or file_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue

                file_str = str(file_path.resolve())

                # Skip if already processed
                if tracker.is_processed(file_str):
                    continue
                try:
                    mtime = file_path.stat().st_mtime
                    if mtime < startup_time:
                        continue
                except Exception:
                    continue
                # Mark as processed
                total_screenshots += 1
                print(f"[NEW] Screenshot detected: {file_path.name}")

                # Extract text via OCR (optional)
                text = extract_text_from_image(file_str)

                # OCR is optional - we still save the image even if OCR fails
                ocr_success += 1

                # Check for junk --> removed since dosen't apply to images much
                # if is_junk_text(text):
                #     print(f"[SKIP] Junk text")
                #     continue

                # Check for exact duplicates
                content_hash = compute_image_hash(file_str)
                existing_id = check_exact_duplicate(content_hash)

                if existing_id is not None:
                    duplicates_skipped += 1
                    print(f"[SKIP] Duplicate text of Item #{existing_id} (total dupes: {duplicates_skipped})")
                    continue

                # Save to database with screenshot data
                with get_session() as session:
                    new_item = Item(
                        text=text,
                        content_hash=content_hash,
                        source="screenshot",
                        blob_uri=file_str  # Store path to original screenshot
                    )
                    session.add(new_item)
                    session.commit()
                    session.refresh(new_item)

                # Index BOTH text vector and image vector
                try:
                    # Text vector from OCR
                    if text != "[No text detected]":
                        text_vector = encode_text_to_vector(text)
                        store.add_text_vector(item_id=new_item.id, vector=text_vector)

                    # Image vector from CLIP
                    image_vector = encode_image(file_str)
                    store.add_image_vector(item_id=new_item.id, vector=image_vector)

                    save_counter += 1


                    store.save()
                    stats = store.get_stats()
                    print(
                        f"[SYSTEM] Indexes saved - Text: {stats['text_vectors']}, Image: {stats['image_vectors']}")
                    tracker.mark_processed(file_str)
                except Exception as e:
                    print(f"[ERROR] Failed to index: {e}")

                # Display confirmation
                if len(text) > 80:
                    shortened_text = text[:80] + "..."
                else:
                    shortened_text = text

                print("[ITEM] Saved Item #" + str(new_item.id) + " [SCREENSHOT] | " + repr(shortened_text))

                # Show stats every 10 items
                if total_screenshots % 10 == 0:
                    print(
                        f"[STATS] Screenshots: {total_screenshots} | OCR Success: {ocr_success} | Failed: {ocr_failed} | Dupes: {duplicates_skipped}"
                    )

            time.sleep(poll_seconds)

    except KeyboardInterrupt:
        print("[SYSTEM] Shutting down...")
        tracker.force_save()
        print("[SYSTEM] Cache saved. Screenshot watcher stopped.")


def main():
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    watch_screenshots(folder_path=folder)


if __name__ == "__main__":
    main()