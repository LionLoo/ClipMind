import os

def create_startup(name="ClipMind", script_path=None):
    if script_path is None:
        script_path = os.path.abspath(__file__)

    startup_folder = os.path.join(
        os.getenv('APPDATA'),
        'Microsoft\\Windows\\Start Menu\\Programs\\Startup'
    )

    bat_path = os.path.join(startup_folder, f"{name}.bat")

    if os.path.exists(bat_path):
        print("ClipMind AutoStart Already Enabled")
        return

    with open(bat_path, "w") as bat_file:
        bat_file.write(f"""@echo off
REM (optional) activate venv here
cd /d {os.path.dirname(script_path)}
python "{script_path}"
""")

    print(f"ClipMind auto-start enabled. Shortcut created at:\n{bat_path}")
