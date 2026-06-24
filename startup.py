"""
startup.py
----------
NEXUS startup module — must be imported FIRST in any entry point.

Ensures correct DLL/native library initialization order on Windows:
  1. chromadb (HNSW native) must init before SQLAlchemy C extensions
  2. Sets up environment variables from .env

Import this before any other NEXUS modules.
"""

from __future__ import annotations

# Step 1: load env vars before anything else
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# Step 2: initialize chromadb client early (loads HNSW native DLLs first)
from vectorstore.chroma_client import get_chroma_client
_chroma = get_chroma_client()

# Step 3: now safe to import everything else
__all__ = ["_chroma"]
