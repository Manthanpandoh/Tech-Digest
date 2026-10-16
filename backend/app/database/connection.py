"""
MongoDB Atlas connection management.
Provides a singleton client and database instance.
"""

import certifi
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.config.settings import settings
from app.utils.logging_config import get_logger

# Configure reliable public DNS fallback for MongoDB Atlas SRV resolution on restricted networks
try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

logger = get_logger(__name__)

# ── Singleton client ──────────────────────────────────────────────────────────

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        if getattr(settings, "USE_MOCK_DB", False) or settings.MONGODB_URI.lower().startswith("mock"):
            try:
                import mongomock
                logger.info("Initializing in-memory MongoDB client (mongomock mode)")
                _client = mongomock.MongoClient()
                return _client
            except ImportError:
                logger.warning("mongomock not installed, falling back to standard client")

        logger.info("Creating MongoDB client (host redacted from logs)")
        _client = MongoClient(
            settings.MONGODB_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=15_000,
            connectTimeoutMS=15_000,
            socketTimeoutMS=15_000,
            retryWrites=True,
            retryReads=True,
        )
    return _client


def get_database():
    return get_client()[settings.DATABASE_NAME]


def test_connection() -> bool:
    """Ping the MongoDB cluster. Returns True on success, False on failure."""
    if getattr(settings, "USE_MOCK_DB", False) or settings.MONGODB_URI.lower().startswith("mock"):
        return True
    try:
        get_client().admin.command("ping")
        logger.info("MongoDB ping successful")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        logger.error("MongoDB connection failed: %s", type(exc).__name__)
        return False
    except Exception as exc:
        logger.error("MongoDB unexpected error: %s", type(exc).__name__)
        return False


def close_connection() -> None:
    """Gracefully close the client — called on application shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")
