"""
PaperSignal — Entrypoint
Run: python main.py
All config from .env
"""

import sys
import os

# Add project root to path so all imports resolve cleanly
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )