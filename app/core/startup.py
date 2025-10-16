import os
import sys


def create_startup(name="ClipMind"):
    """
    Creates a startup shortcut that runs ClipMind backend + GUI on Windows boot
    """
    # Get project root (go up 2 levels from app/core/)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))

    # Path to the Python backend script
    backend_script = os.path.join(project_root, "run_clipmind.py")

    # Path to the Tauri app (adjust based on your build location)
    # Option 1: If you've built the .exe
    tauri_exe = os.path.join(project_root, "clipmind-ui", "src-tauri", "target", "release", "clipmind-ui.exe")

    # Option 2: If running in dev mode (uncomment if you want this)
    # tauri_dev_cmd = f'cd /d "{os.path.join(project_root, "clipmind-ui")}" && npm run tauri dev'

    if not os.path.exists(backend_script):
        print(f"ERROR: run_clipmind.py not found at {backend_script}")
        return False

    # Windows Startup folder
    startup_folder = os.path.join(
        os.getenv('APPDATA'),
        'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
    )

    # Ensure startup folder exists
    os.makedirs(startup_folder, exist_ok=True)

    bat_path = os.path.join(startup_folder, f"{name}.bat")

    if os.path.exists(bat_path):
        print(f"[STARTUP] ✓ ClipMind already in startup folder: {bat_path}")
        return True

    # Get Python executable path
    python_exe = sys.executable

    # Create batch file that runs both backend AND GUI
    with open(bat_path, "w") as bat_file:
        # Check if built .exe exists
        if os.path.exists(tauri_exe):
            # Use the built executable
            bat_file.write(f"""@echo off
REM ClipMind Auto-Startup Script (Backend + GUI)
cd /d "{project_root}"

REM Start Python backend in background
start /B "" "{python_exe}" "{backend_script}"

REM Wait 3 seconds for backend to initialize
timeout /t 3 /nobreak >nul

REM Start Tauri GUI
start "" "{tauri_exe}"

exit
""")
        else:
            # Use dev mode (npm run tauri dev)
            bat_file.write(f"""@echo off
REM ClipMind Auto-Startup Script (Backend + GUI - Dev Mode)
cd /d "{project_root}"

REM Start Python backend in background
start /B "" "{python_exe}" "{backend_script}"

REM Wait 3 seconds for backend to initialize
timeout /t 3 /nobreak >nul

REM Start Tauri GUI in dev mode
cd /d "{os.path.join(project_root, "clipmind-ui")}"
start "" npm run tauri dev

exit
""")

    print(f"[STARTUP] ✓ ClipMind auto-start enabled (Backend + GUI)!")
    print(f"[STARTUP]   Shortcut: {bat_path}")
    print(f"[STARTUP]   Backend: {backend_script}")
    if os.path.exists(tauri_exe):
        print(f"[STARTUP]   GUI: {tauri_exe}")
    else:
        print(f"[STARTUP]   GUI: Dev mode (npm run tauri dev)")
    return True


def remove_startup(name="ClipMind"):
    """Remove ClipMind from Windows startup"""
    startup_folder = os.path.join(
        os.getenv('APPDATA'),
        'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
    )

    bat_path = os.path.join(startup_folder, f"{name}.bat")

    if os.path.exists(bat_path):
        os.remove(bat_path)
        print(f"[STARTUP] ✓ ClipMind removed from startup")
        return True
    else:
        print(f"[STARTUP] ClipMind not found in startup")
        return False


if __name__ == "__main__":
    # Run this script directly to add ClipMind to startup
    create_startup()