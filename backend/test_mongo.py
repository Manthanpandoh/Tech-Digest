from pymongo import MongoClient
from dotenv import load_dotenv
import certifi
import os

try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

load_dotenv()

uri = os.getenv("MONGODB_URI")

# Mask URI credentials for logging
if uri:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        safe_uri = f"{parsed.scheme}://[credentials]@{parsed.hostname}{parsed.path}"
        print("URI:", safe_uri)
    except Exception:
        print("URI: [configured]")
else:
    print("URI: NOT SET")

try:
    client = MongoClient(
        uri,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
    )

    print("Pinging MongoDB...")
    client.admin.command("ping")

    print("[SUCCESS] Connected Successfully")

except Exception as e:
    print("[ERROR] Connection Failed")
    print(type(e).__name__)
    print(e)