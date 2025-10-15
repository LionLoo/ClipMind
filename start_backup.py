"""
Start the ClipMind backend server
"""
import uvicorn
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

if __name__ == "__main__":
    print("Starting ClipMind backend on http://localhost:8000")
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )