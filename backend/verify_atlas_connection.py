"""
TechPulse AI — MongoDB Atlas Real Connection Verification Tool.
Tests live connection, authentication, write, read, and cleanup permissions
WITHOUT revealing passwords or credentials in logs or stdout.
"""

import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
)

# Configure reliable public DNS fallback for MongoDB Atlas SRV resolution
try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

# Load environment
backend_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(backend_dir, ".env")
load_dotenv(env_path, override=True)

uri = os.getenv("MONGODB_URI", "").strip()
db_name = os.getenv("DATABASE_NAME", "techpulse_ai").strip()


def mask_uri(raw_uri: str) -> str:
    """Return URI with credentials masked for safe terminal display."""
    if not raw_uri:
        return "[NOT SET]"
    try:
        parsed = urlparse(raw_uri)
        if parsed.hostname:
            return f"{parsed.scheme}://[CREDENTIALS_HIDDEN]@{parsed.hostname}{parsed.path}"
        return f"{raw_uri[:15]}...[CREDENTIALS_HIDDEN]..."
    except Exception:
        return "[CONFIGURED_URI_REDACTED]"


def sanitize_msg(text: str) -> str:
    """Ensure no password or sensitive query params appear in stdout."""
    if not text:
        return ""
    try:
        parsed = urlparse(uri)
        if parsed.password and parsed.password in text:
            text = text.replace(parsed.password, "[REDACTED_PASSWORD]")
    except Exception:
        pass
    return text


print("=" * 65)
print("  TECHPULSE AI -- MONGODB ATLAS LIVE CONNECTION VERIFICATION")
print("=" * 65)
print(f"Target Cluster : {mask_uri(uri)}")
print(f"Target Database: {db_name}")
print(f"Driver         : PyMongo 4.17.0 (Python 3.12.10, TLS via certifi)")
print("-" * 65)

if not uri:
    print("[FAIL] MONGODB_URI is not set in backend/.env")
    sys.exit(1)

print("\n[Step 1/4] Establishing secure TLS connection and pinging cluster...")
try:
    client = MongoClient(
        uri,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
        retryWrites=True,
    )
    # Ping
    ping_res = client.admin.command("ping")
    print("  -> [PASS] Ping successful! Cluster acknowledged:", ping_res)

    # Step 2: Database and Write Verification
    print("\n[Step 2/4] Testing write permissions on database '%s'..." % db_name)
    db = client[db_name]
    probe_col = db["_connection_probe"]
    test_doc = {
        "_probe": "techpulse_atlas_verification",
        "timestamp": datetime.now(timezone.utc),
        "status": "testing_write",
    }
    insert_res = probe_col.insert_one(test_doc)
    doc_id = insert_res.inserted_id
    print("  -> [PASS] Write successful! Inserted probe ID:", doc_id)

    # Step 3: Read Verification
    print("\n[Step 3/4] Testing read permissions...")
    found = probe_col.find_one({"_id": doc_id})
    if found and found.get("_probe") == "techpulse_atlas_verification":
        print("  -> [PASS] Read successful! Retrieved probe document correctly.")
    else:
        print("  -> [FAIL] Document inserted but could not be read back.")
        sys.exit(1)

    # Step 4: Cleanup Verification
    print("\n[Step 4/4] Cleaning up test probe...")
    delete_res = probe_col.delete_one({"_id": doc_id})
    print("  -> [PASS] Cleanup successful! Deleted count:", delete_res.deleted_count)

    print("\n" + "=" * 65)
    print("  RESULT: MONGODB ATLAS CONNECTION VERIFIED SUCCESSFULLY!")
    print("  Database read/write permissions are confirmed.")
    print("=" * 65)
    client.close()
    sys.exit(0)

except OperationFailure as exc:
    if getattr(exc, "code", None) == 18 or "auth" in str(exc).lower():
        print("\n[FAIL] Authentication Failed:")
        print("  The database username or password in MONGODB_URI is incorrect.")
        print("  Tips:")
        print("  - If password contains special characters (@, :, /, ?, #), URL-encode them.")
        print("  - Check Atlas Database Access > Database Users in MongoDB Atlas.")
    else:
        print(f"\n[FAIL] Database Operation Failed ({exc.code}): {sanitize_msg(str(exc))}")
    sys.exit(1)

except ServerSelectionTimeoutError as exc:
    print("\n[FAIL] Server Selection Timeout (Cannot reach cluster):")
    print("  Could not reach cluster within 10 seconds.")
    print("  Details:", sanitize_msg(str(exc)))
    print("  Most common cause: Network Access / IP Whitelist.")
    print("  Tips:")
    print("  - In Atlas, go to 'Network Access' -> click 'Add IP Address'.")
    print("  - Click 'Allow Access from Anywhere' (0.0.0.0/0) or 'Add Current IP Address'.")
    sys.exit(1)

except ConfigurationError as exc:
    print("\n[FAIL] Configuration / DNS Error:")
    print("  Details:", sanitize_msg(str(exc)))
    print("  Tips:")
    print("  - Verify the cluster hostname in the connection string.")
    print("  - Check for extra spaces or typos in MONGODB_URI.")
    sys.exit(1)

except Exception as exc:
    print(f"\n[FAIL] Unexpected Connection Error ({type(exc).__name__}):")
    print("  Details:", sanitize_msg(str(exc)))
    sys.exit(1)
