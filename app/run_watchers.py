# Purpose: Runs both clipboard and screenshot watchers at the same time
# This is an alternative to run_clipmind.py - runs ONLY the watchers, no API server

import multiprocessing
import sys
import time


def run_clipboard_watcher():
    """Run clipboard watcher in one process"""
    try:
        from app.ingest.main import watch_clipboard
        watch_clipboard()
    except KeyboardInterrupt:
        print("\n[CLIPBOARD] Watcher stopped")
    except Exception as e:
        print(f"[ERROR] Clipboard watcher failed: {e}")


def run_screenshot_watcher():
    """Run the screenshot watcher in another process"""
    try:
        from app.ingest.screenshot_watcher import watch_screenshots
        watch_screenshots()
    except KeyboardInterrupt:
        print("\n[SCREENSHOT] Watcher stopped")
    except Exception as e:
        print(f"[ERROR] Screenshot watcher failed: {e}")


def main():
    """Starts all the processes in parallel"""
    print("=" * 60)
    print("ClipMind - Starting All Watchers")
    print("=" * 60)
    print()
    print("[SYSTEM] Starting clipboard watcher...")
    print("[SYSTEM] Starting screenshot watcher...")
    print()
    print("Press Ctrl+C to stop all watchers")
    print("=" * 60)
    print()

    # Create processes for each watcher
    clipboard_process = multiprocessing.Process(
        target=run_clipboard_watcher,
        name="ClipboardWatcher"
    )

    screenshot_process = multiprocessing.Process(
        target=run_screenshot_watcher,
        name="ScreenshotWatcher"
    )

    # Start both processes
    clipboard_process.start()
    screenshot_process.start()

    try:
        # Keep main process alive and monitor child processes
        while True:
            # Check if either process has died and restart if needed
            if not clipboard_process.is_alive():
                print("[WARN] Clipboard watcher stopped unexpectedly")
                clipboard_process = multiprocessing.Process(
                    target=run_clipboard_watcher,
                    name="ClipboardWatcher"
                )
                clipboard_process.start()
                print("[SYSTEM] Clipboard watcher restarted")

            if not screenshot_process.is_alive():
                print("[WARN] Screenshot watcher stopped unexpectedly")
                screenshot_process = multiprocessing.Process(
                    target=run_screenshot_watcher,
                    name="ScreenshotWatcher"
                )
                screenshot_process.start()
                print("[SYSTEM] Screenshot watcher restarted")

            time.sleep(5)  # Check every 5 seconds

    except KeyboardInterrupt:
        print("\n")
        print("=" * 60)
        print("[SYSTEM] Shutting down all watchers...")
        print("=" * 60)

        # Terminate both processes
        clipboard_process.terminate()
        screenshot_process.terminate()

        # Wait for them to finish
        clipboard_process.join(timeout=5)
        screenshot_process.join(timeout=5)

        # Force kill if they don't stop
        if clipboard_process.is_alive():
            clipboard_process.kill()
        if screenshot_process.is_alive():
            screenshot_process.kill()

        print("[SYSTEM] All watchers stopped. Exiting ClipMind, Goodbye!")


if __name__ == "__main__":
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()
    main()