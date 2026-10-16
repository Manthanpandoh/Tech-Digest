"""
Pytest configuration and shared fixtures.

All tests in this suite mock external services (MongoDB, OpenRouter, WhatsApp)
so they can run without real credentials or network access.
"""

import os
import pytest

# Point tests at a non-existent DB so accidental real connections fail loudly
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("DATABASE_NAME", "techpulse_test")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("WHATSAPP_DRY_RUN", "true")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """FastAPI test client — no real DB or LLM calls."""
    # Import after env vars are set
    from unittest.mock import patch, MagicMock

    # Patch DB connection so startup doesn't try to connect
    with patch("app.database.connection.test_connection", return_value=True), \
         patch("app.database.repository.ensure_indexes"):
        import main
        with TestClient(main.app, raise_server_exceptions=True) as c:
            yield c
