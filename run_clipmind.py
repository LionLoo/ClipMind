"""
Complete ClipMind startup script
Runs everything: DB init, index rebuild, clipboard monitor, screenshot monitor, API server
Auto-adds to Windows startup on first run
"""
import subprocess
import sys
import time
from pathlib import Path
import threading
import os

# Add app to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

def run_db_init():
    """Initialize database"""
    print("[STARTUP] Initializing database...")
    from app.db.session import init_db
    init_db()
    print("[STARTUP] ✓ Database initialized")

def run_index_rebuild():
    """Rebuild vector indexes if they don't exist"""
    try:
        from app.index.rebuild_from_db import rebuild_index
        rebuild_index()
        print("[STARTUP] ✓ Vector indexes rebuilt")
    except Exception as e:
        print(f"[STARTUP] ⚠ Index rebuild failed: {e}")

def run_clipboard_monitor():
    """Start clipboard monitor in background thread"""
    print("[STARTUP] Starting clipboard monitor...")

    def monitor():
        try:
            from app.ingest.main import watch_clipboard
            watch_clipboard()
        except Exception as e:
            print(f"[STARTUP] ✗ Clipboard monitor failed: {e}")

    thread = threading.Thread(target=monitor, daemon=True, name="ClipboardMonitor")
    thread.start()
    print("[STARTUP] ✓ Clipboard monitor started (background)")

def run_screenshot_monitor():
    """Start screenshot monitor in background thread"""
    print("[STARTUP] Starting screenshot monitor...")

    def monitor():
        try:
            from app.ingest.screenshot_watcher import watch_screenshots
            watch_screenshots()
        except Exception as e:
            print(f"[STARTUP] ✗ Screenshot monitor failed: {e}")

    thread = threading.Thread(target=monitor, daemon=True, name="ScreenshotMonitor")
    thread.start()
    print("[STARTUP] ✓ Screenshot monitor started (background)")

def setup_windows_startup():
    """Add ClipMind to Windows startup (runs silently in background)"""
    if sys.platform != "win32":
        return  # Only for Windows

    try:
        from app.core.startup import create_startup
        create_startup()
    except Exception as e:
        print(f"[STARTUP] ⚠ Failed to setup auto-start: {e}")

def run_api_server():
    """Start FastAPI server"""
    print("[STARTUP] Starting API server on http://localhost:8000...")
    import uvicorn
    uvicorn.run(
        "app.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload since we're managing everything
        log_level="info"
    )

if __name__ == "__main__":
    print("=" * 60)
    print("ClipMind - Complete Startup")
    print("=" * 60)

    # 0. Auto-add to Windows startup (silent, only adds if not already there)
    setup_windows_startup()

    # 1. Initialize DB
    run_db_init()

    # 2. Rebuild indexes from existing data
    run_index_rebuild()

    # 3. Start clipboard monitor (background)
    run_clipboard_monitor()

    # 4. Start screenshot monitor (background)
    run_screenshot_monitor()

    # Give monitors a moment to initialize
    time.sleep(1)

    print("=" * 60)
    print("[STARTUP] ✓ All services running!")
    print("[STARTUP] Press Ctrl+C to stop")
    print("=" * 60)

    # 5. Start API server (blocks here)
    try:
        run_api_server()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping ClipMind...")
        sys.exit(0)