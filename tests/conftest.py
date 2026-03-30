"""
tests/conftest.py – Pytest configuration for CodePerfectAuditor tests.

Adds backend to sys.path and sets env vars so config.py validates without
a real OpenAI key or running database.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Minimal env vars required by pydantic-settings (Settings validates on import)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-unit-tests")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_codeperfect.db")
os.environ.setdefault("CHROMA_PERSIST_DIR", "./test_chroma_store")
