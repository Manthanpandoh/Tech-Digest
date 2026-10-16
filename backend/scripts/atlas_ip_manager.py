#!/usr/bin/env python3
"""
TechPulse AI — MongoDB Atlas Temporary IP Access List Manager.

Manages short-lived IP allowlist entries in MongoDB Atlas for GitHub Actions runners
using the MongoDB Atlas Administration API (Digest Authentication) with automatic
expiry fallback, propagation verification, and strict race-condition safety.

STRICT SECURITY RULES:
- Never exposes secrets in stdout, stderr, process lists, or exception logs.
- Never adds 0.0.0.0/0.
- Never deletes an access list entry unless its comment matches the unique run identifier.
- Always sets deleteAfterDate as an automatic fallback if runner is abruptly terminated.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import logging
import os
import re
import sys
import time
from urllib.parse import quote, urlparse

import requests
from requests.auth import HTTPDigestAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("atlas_ip_manager")

# ── Custom Exceptions ──────────────────────────────────────────────────────────


class AtlasIPManagerError(Exception):
    """Base exception for Atlas IP Manager."""


class InvalidIPAddressError(AtlasIPManagerError):
    """Raised when an IP address is invalid, private, reserved, or malformed."""


class AtlasAPIError(AtlasIPManagerError):
    """Raised when Atlas Administration API returns an error."""


class AtlasAuthError(AtlasAPIError):
    """Raised when Atlas Admin API authentication or authorization fails."""


class AtlasPropagationTimeoutError(AtlasAPIError):
    """Raised when access list propagation does not become ACTIVE in time."""


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_ATLAS_BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
DEFAULT_STATE_FILE = ".atlas_run_state.json"
DEFAULT_IP_DISCOVERY_SERVICES = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://icanhazip.com",
]

# ── Redaction and Masking Helpers ─────────────────────────────────────────────


def mask_secret(secret: str | None, visible_chars: int = 4) -> str:
    """Mask a secret for display without leaking characters."""
    if not secret:
        return "[NOT SET]"
    if len(secret) <= visible_chars * 2:
        return "[REDACTED]"
    return f"{secret[:visible_chars]}...[REDACTED]...{secret[-visible_chars:]}"


def mask_uri(raw_uri: str | None) -> str:
    """Mask credentials in MongoDB connection URI."""
    if not raw_uri:
        return "[NOT SET]"
    try:
        parsed = urlparse(raw_uri)
        if parsed.hostname:
            return f"{parsed.scheme}://[CREDENTIALS_HIDDEN]@{parsed.hostname}{parsed.path}"
        return f"{raw_uri[:10]}...[CREDENTIALS_HIDDEN]"
    except Exception:
        return "[URI_REDACTED]"


def sanitize_text(text: str, secrets: list[str]) -> str:
    """Remove known secrets from any error message or text output."""
    if not text:
        return ""
    sanitized = text
    for secret in secrets:
        if secret and len(secret) > 3:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


# ── IP Discovery and Validation ───────────────────────────────────────────────


def validate_public_ipv4(ip_str: str) -> str:
    """
    Validate that an input string is a strictly valid public IPv4 address.
    Rejects:
    - Non-IPv4 addresses (IPv6)
    - Private addresses (RFC 1918)
    - Loopback addresses (127.0.0.0/8)
    - Link-local addresses (169.254.0.0/16)
    - Multicast addresses (224.0.0.0/4)
    - Reserved addresses (240.0.0.0/4)
    - Carrier-grade NAT (100.64.0.0/10)
    - Unspecified addresses (0.0.0.0)
    - Broadcast address (255.255.255.255)
    - Malformed strings or non-numeric octets
    """
    if not ip_str or not isinstance(ip_str, str):
        raise InvalidIPAddressError("IP address string cannot be empty or non-string.")

    clean_ip = ip_str.strip()

    # Reject leading/trailing slashes or CIDR notations at this raw validation level
    if "/" in clean_ip:
        clean_ip = clean_ip.split("/")[0].strip()

    try:
        ip = ipaddress.ip_address(clean_ip)
    except ValueError as exc:
        raise InvalidIPAddressError(f"Malformed IP address format: {clean_ip}") from exc

    if not isinstance(ip, ipaddress.IPv4Address):
        raise InvalidIPAddressError(f"Only IPv4 addresses are supported. Got IPv6: {clean_ip}")

    # Explicit safety checks in specific-to-general order
    if ip == ipaddress.IPv4Address("0.0.0.0"):
        raise InvalidIPAddressError("0.0.0.0 is strictly prohibited.")
    if ip == ipaddress.IPv4Address("255.255.255.255"):
        raise InvalidIPAddressError("Broadcast address 255.255.255.255 is strictly prohibited.")
    if ip.is_loopback:
        raise InvalidIPAddressError(f"Loopback IP address is prohibited: {clean_ip}")
    if ip.is_link_local:
        raise InvalidIPAddressError(f"Link-local IP address is prohibited: {clean_ip}")
    if ip.is_multicast:
        raise InvalidIPAddressError(f"Multicast IP address is prohibited: {clean_ip}")
    if ip.is_reserved:
        raise InvalidIPAddressError(f"Reserved IP address range is prohibited: {clean_ip}")
    if ip.is_unspecified:
        raise InvalidIPAddressError(f"Unspecified IP address is prohibited: {clean_ip}")

    # Check Carrier-Grade NAT (RFC 6598: 100.64.0.0/10)
    cgnat_network = ipaddress.ip_network("100.64.0.0/10")
    if ip in cgnat_network:
        raise InvalidIPAddressError(f"Carrier-grade NAT IP (100.64.0.0/10) is prohibited: {clean_ip}")

    # Check RFC 1918 and test/documentation networks
    if ip.is_private:
        raise InvalidIPAddressError(f"Private IP address (RFC 1918) is prohibited: {clean_ip}")

    return str(ip)


def to_cidr_32(ip_str: str) -> str:
    """Validate public IPv4 and return as /32 CIDR string."""
    validated = validate_public_ipv4(ip_str)
    return f"{validated}/32"


def fetch_public_ip(
    timeout: float = 5.0,
    endpoints: list[str] | None = None,
    session: requests.Session | None = None,
) -> str:
    """
    Query trusted HTTPS endpoints to discover runner's outbound public IPv4 address.
    Tries endpoints in order until a valid public IPv4 is returned.
    """
    services = endpoints or DEFAULT_IP_DISCOVERY_SERVICES
    client = session or requests.Session()
    last_error: Exception | None = None

    for endpoint in services:
        try:
            logger.info("Attempting public IP discovery via: %s", endpoint)
            resp = client.get(endpoint, timeout=timeout)
            if resp.status_code == 200:
                raw_ip = resp.text.strip()
                validated_ip = validate_public_ipv4(raw_ip)
                logger.info("Discovered valid public IPv4: %s", validated_ip)
                return validated_ip
            else:
                logger.warning(
                    "Service %s returned HTTP %s. Trying next service.",
                    endpoint,
                    resp.status_code,
                )
        except Exception as exc:
            last_error = exc
            logger.warning("Failed to discover IP via %s: %s", endpoint, str(exc))

    raise AtlasIPManagerError(
        f"All public IP discovery services failed. Last error: {last_error}"
    )


# ── Run Identifier and Comment Generation ─────────────────────────────────────


def generate_run_comment(
    run_id: str | None = None,
    run_attempt: str | None = None,
    prefix: str = "gh-actions",
) -> str:
    """
    Generate a unique, verifiable comment for this workflow run.
    Ensures safe characters and maximum length constraints (<= 80 chars for Atlas).
    """
    # Pull from environment if not provided explicitly
    r_id = run_id or os.getenv("GITHUB_RUN_ID")
    r_att = run_attempt or os.getenv("GITHUB_RUN_ATTEMPT", "1")

    if r_id:
        # Sanitize to alphanumeric + hyphens
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(r_id))
        clean_att = re.sub(r"[^a-zA-Z0-9_-]", "", str(r_att))
        comment = f"{prefix}-{clean_id}-{clean_att}"
    else:
        # Fallback to UTC timestamp + random token for local/manual runs
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        import uuid
        token = uuid.uuid4().hex[:8]
        comment = f"{prefix}-manual-{timestamp}-{token}"

    # Atlas comments limit is 80 characters
    return comment[:80]


# ── MongoDB Atlas Administration API Client ───────────────────────────────────


class AtlasAccessListManager:
    """
    Client for managing Project IP Access Lists via Atlas Admin API v2.
    Uses HTTP Digest Authentication.
    """

    def __init__(
        self,
        project_id: str,
        public_key: str,
        private_key: str,
        base_url: str = DEFAULT_ATLAS_BASE_URL,
        session: requests.Session | None = None,
    ):
        if not project_id or not project_id.strip():
            raise AtlasIPManagerError("ATLAS_PROJECT_ID (groupId) is required.")
        if not public_key or not public_key.strip():
            raise AtlasIPManagerError("ATLAS_PUBLIC_KEY is required.")
        if not private_key or not private_key.strip():
            raise AtlasIPManagerError("ATLAS_PRIVATE_KEY is required.")

        self.project_id = project_id.strip()
        self.public_key = public_key.strip()
        self.private_key = private_key.strip()
        self.base_url = base_url.rstrip("/")

        self._secrets = [self.public_key, self.private_key]

        self.session = session or requests.Session()
        self.session.auth = HTTPDigestAuth(self.public_key, self.private_key)
        self.session.headers.update({
            "Accept": "application/vnd.atlas.2023-01-01+json",
            "Content-Type": "application/json",
        })

    def _sanitize(self, msg: str) -> str:
        return sanitize_text(msg, self._secrets)

    def _handle_response_errors(self, response: requests.Response, context: str) -> None:
        """Inspect HTTP response and raise appropriate sanitized exceptions."""
        if response.status_code in (200, 201, 202, 204):
            return

        error_details = ""
        try:
            body = response.json()
            error_details = body.get("detail") or body.get("error") or str(body)
        except Exception:
            error_details = response.text[:200]

        sanitized_details = self._sanitize(error_details)

        if response.status_code == 401:
            raise AtlasAuthError(
                f"Atlas API Authentication Failed during {context} (HTTP 401). "
                "Check ATLAS_PUBLIC_KEY and ATLAS_PRIVATE_KEY."
            )
        if response.status_code == 403:
            raise AtlasAuthError(
                f"Atlas API Authorization Failed during {context} (HTTP 403): {sanitized_details}. "
                "Check that the API Key has Project Network Access Manager (or Project Owner) role, "
                "and ensure the API Key does not have an IP access list restriction blocking the runner."
            )
        if response.status_code == 404:
            raise AtlasAPIError(
                f"Atlas resource not found during {context} (HTTP 404): {sanitized_details}"
            )

        raise AtlasAPIError(
            f"Atlas API error during {context} (HTTP {response.status_code}): {sanitized_details}"
        )

    def get_entry(self, cidr_or_ip: str) -> dict | None:
        """
        Fetch access list entry details.
        Returns entry dict if found, or None if 404.
        """
        encoded_entry = quote(cidr_or_ip, safe="")
        url = f"{self.base_url}/groups/{self.project_id}/accessList/{encoded_entry}"

        try:
            resp = self.session.get(url, timeout=10.0)
            if resp.status_code == 404:
                return None
            self._handle_response_errors(resp, f"get_entry({cidr_or_ip})")
            return resp.json()
        except AtlasAPIError:
            raise
        except Exception as exc:
            raise AtlasAPIError(
                f"Network error querying entry {cidr_or_ip}: {self._sanitize(str(exc))}"
            ) from exc

    def list_entries(self) -> list[dict]:
        """
        Fetch all access list entries for this project.
        Returns list of entry dicts.
        """
        url = f"{self.base_url}/groups/{self.project_id}/accessList"
        try:
            resp = self.session.get(url, timeout=10.0)
            self._handle_response_errors(resp, "list_entries")
            data = resp.json()
            return data.get("results", [])
        except AtlasAPIError:
            raise
        except Exception as exc:
            raise AtlasAPIError(
                f"Network error listing access list entries: {self._sanitize(str(exc))}"
            ) from exc

    def find_entry_by_comment(self, comment: str) -> dict | None:
        """
        Locate an access list entry matching a specific comment.
        Returns entry dict if found, or None.
        """
        if not comment:
            return None
        entries = self.list_entries()
        for entry in entries:
            if entry.get("comment") == comment:
                return entry
        return None

    def get_entry_status(self, cidr_or_ip: str) -> str:
        """
        Fetch status of an access list entry.
        Returns status string: e.g. 'ACTIVE', 'PENDING', 'FAILED', or 'NOT_FOUND'.
        """
        encoded_entry = quote(cidr_or_ip, safe="")
        url = f"{self.base_url}/groups/{self.project_id}/accessList/{encoded_entry}/status"

        try:
            resp = self.session.get(url, timeout=10.0)
            if resp.status_code == 404:
                return "NOT_FOUND"
            self._handle_response_errors(resp, f"get_entry_status({cidr_or_ip})")
            data = resp.json()
            return data.get("status", "UNKNOWN")
        except AtlasAPIError:
            raise
        except Exception as exc:
            raise AtlasAPIError(
                f"Network error checking status of {cidr_or_ip}: {self._sanitize(str(exc))}"
            ) from exc

    def create_access_list_entry(
        self,
        cidr_or_ip: str,
        comment: str,
        duration_seconds: int = 3600,
    ) -> dict:
        """
        Create a temporary Project IP access list entry with explicit short expiry.
        Calculates deleteAfterDate = current_utc_time + duration_seconds.
        """
        url = f"{self.base_url}/groups/{self.project_id}/accessList"

        now_utc = datetime.now(timezone.utc)
        delete_after = (now_utc + timedelta(seconds=duration_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Format payload: use cidrBlock if / is present, else ipAddress
        entry_payload: dict[str, str] = {
            "comment": comment,
            "deleteAfterDate": delete_after,
        }
        if "/" in cidr_or_ip:
            entry_payload["cidrBlock"] = cidr_or_ip
        else:
            entry_payload["ipAddress"] = cidr_or_ip

        payload = [entry_payload]

        logger.info(
            "Creating Atlas temporary IP access entry: %s (comment='%s', deleteAfterDate=%s)",
            cidr_or_ip,
            comment,
            delete_after,
        )

        try:
            resp = self.session.post(url, json=payload, timeout=15.0)

            # Handle 409 Conflict (entry already exists)
            if resp.status_code == 409:
                logger.warning(
                    "Atlas returned HTTP 409 Conflict: Entry for %s already exists.",
                    cidr_or_ip,
                )
                existing = self.get_entry(cidr_or_ip)
                if existing:
                    existing_comment = existing.get("comment", "")
                    if existing_comment == comment:
                        logger.info(
                            "Existing entry comment matches our run ID ('%s'). Reusing entry.",
                            comment,
                        )
                        return {
                            "status": "reused",
                            "created_by_this_run": True,
                            "entry": existing,
                            "deleteAfterDate": existing.get("deleteAfterDate"),
                        }
                    else:
                        logger.warning(
                            "Existing entry comment ('%s') differs from our run ID ('%s'). "
                            "Runner will utilize the existing IP allowlist but will NOT delete it during cleanup.",
                            existing_comment,
                            comment,
                        )
                        return {
                            "status": "shared_conflict",
                            "created_by_this_run": False,
                            "entry": existing,
                            "deleteAfterDate": existing.get("deleteAfterDate"),
                        }

            self._handle_response_errors(resp, f"create_access_list_entry({cidr_or_ip})")
            response_data = resp.json()
            return {
                "status": "created",
                "created_by_this_run": True,
                "response": response_data,
                "deleteAfterDate": delete_after,
            }

        except AtlasAPIError:
            raise
        except Exception as exc:
            raise AtlasAPIError(
                f"Network error creating access list entry {cidr_or_ip}: {self._sanitize(str(exc))}"
            ) from exc

    def wait_for_propagation(
        self,
        cidr_or_ip: str,
        max_retries: int = 15,
        initial_delay: float = 2.0,
        backoff_factor: float = 1.5,
        max_delay: float = 15.0,
    ) -> bool:
        """
        Poll Atlas entry status until it reaches 'ACTIVE' using bounded retries and exponential backoff.
        """
        logger.info("Waiting for Atlas access list entry %s to become ACTIVE...", cidr_or_ip)
        current_delay = initial_delay

        for attempt in range(1, max_retries + 1):
            try:
                status = self.get_entry_status(cidr_or_ip)
                logger.info(
                    "Propagation check (attempt %d/%d): status = '%s'",
                    attempt,
                    max_retries,
                    status,
                )

                if status == "ACTIVE":
                    logger.info("Access list entry %s is ACTIVE across cluster providers.", cidr_or_ip)
                    return True
                elif status == "FAILED":
                    raise AtlasAPIError(
                        f"Atlas reported access list entry {cidr_or_ip} propagation status: FAILED"
                    )

            except AtlasAuthError:
                raise
            except AtlasAPIError as api_err:
                if "FAILED" in str(api_err):
                    raise
                logger.warning("Transient error during status poll: %s", str(api_err))

            if attempt < max_retries:
                time.sleep(current_delay)
                current_delay = min(current_delay * backoff_factor, max_delay)

        raise AtlasPropagationTimeoutError(
            f"Timed out after {max_retries} attempts waiting for {cidr_or_ip} to propagate to ACTIVE state."
        )

    def delete_access_list_entry(
        self,
        cidr_or_ip: str,
        expected_comment: str | None = None,
    ) -> bool:
        """
        Safely remove an access list entry.
        RACE CONDITION & CONCURRENCY PROTECTION:
        Before deleting, queries the entry to verify that its comment strictly matches
        the expected_comment. If comments do not match, skips deletion!
        """
        encoded_entry = quote(cidr_or_ip, safe="")
        url = f"{self.base_url}/groups/{self.project_id}/accessList/{encoded_entry}"

        logger.info("Beginning safe cleanup for access list entry: %s", cidr_or_ip)

        # 1. Inspect existing entry
        existing = self.get_entry(cidr_or_ip)
        if not existing:
            logger.info("Entry %s not found on Atlas (already deleted or expired).", cidr_or_ip)
            return True

        current_comment = existing.get("comment", "")

        # 2. Verify comment match
        if expected_comment is not None and current_comment != expected_comment:
            logger.warning(
                "SAFETY CHECK ABORT: Entry %s has comment '%s', but expected '%s'. "
                "Skipping deletion to prevent removing an entry owned by another workflow run or user.",
                cidr_or_ip,
                current_comment,
                expected_comment,
            )
            return False

        # 3. Call DELETE
        logger.info(
            "Comment verified ('%s'). Sending DELETE request for %s...",
            current_comment,
            cidr_or_ip,
        )
        try:
            resp = self.session.delete(url, timeout=15.0)
            if resp.status_code == 404:
                logger.info("Entry %s already deleted (HTTP 404).", cidr_or_ip)
                return True

            self._handle_response_errors(resp, f"delete_access_list_entry({cidr_or_ip})")
            logger.info("Atlas acknowledged deletion of %s (HTTP %d).", cidr_or_ip, resp.status_code)

            # 4. Verification of deletion
            verify_resp = self.get_entry(cidr_or_ip)
            if verify_resp is None:
                logger.info("Verified entry %s is completely removed from Atlas.", cidr_or_ip)
            else:
                logger.info(
                    "Entry %s status after delete: %s (will be purged by Atlas).",
                    cidr_or_ip,
                    verify_resp.get("status", "DELETING"),
                )

            return True

        except AtlasAPIError:
            raise
        except Exception as exc:
            raise AtlasAPIError(
                f"Network error deleting entry {cidr_or_ip}: {self._sanitize(str(exc))}"
            ) from exc


# ── State File Persistence ────────────────────────────────────────────────────


def save_state(state_file: str, data: dict) -> None:
    """Save execution state locally for cleanup step."""
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved runner state to: %s", state_file)
    except Exception as exc:
        logger.warning("Failed to save state file %s: %s", state_file, exc)


def load_state(state_file: str) -> dict | None:
    """Load runner state from local state file."""
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load state file %s: %s", state_file, exc)
        return None


def clear_state(state_file: str) -> None:
    """Delete state file on successful cleanup."""
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
            logger.info("Removed state file: %s", state_file)
        except Exception as exc:
            logger.warning("Failed to remove state file %s: %s", state_file, exc)


# ── MongoDB Connectivity Verification ─────────────────────────────────────────


def verify_mongodb_connectivity(
    uri: str | None = None,
    timeout_ms: int = 10000,
) -> bool:
    """
    Connect to MongoDB cluster and verify ping without leaking credentials.
    """
    target_uri = uri or os.getenv("MONGODB_URI", "")
    if not target_uri:
        logger.error("MONGODB_URI is not set. Cannot perform database connectivity verification.")
        return False

    import certifi
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError

    masked = mask_uri(target_uri)
    logger.info("Performing MongoDB cluster connectivity verification to %s...", masked)

    client = None
    try:
        client = MongoClient(
            target_uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            retryWrites=True,
        )
        ping_res = client.admin.command("ping")
        logger.info("MongoDB cluster ping successful! Cluster response: %s", ping_res)
        return True
    except OperationFailure as exc:
        logger.error("MongoDB authentication/operation failure: %s", exc.code)
        return False
    except ServerSelectionTimeoutError as exc:
        logger.error("MongoDB server selection timeout (IP allowlist or network block).")
        return False
    except ConnectionFailure as exc:
        logger.error("MongoDB connection failure: %s", type(exc).__name__)
        return False
    except Exception as exc:
        logger.error("Unexpected error during MongoDB verification: %s", type(exc).__name__)
        return False
    finally:
        if client:
            client.close()


# ── CLI Commands ──────────────────────────────────────────────────────────────


def cmd_add(args: argparse.Namespace) -> int:
    """Execute temporary IP addition flow."""
    project_id = os.getenv("ATLAS_PROJECT_ID", "")
    public_key = os.getenv("ATLAS_PUBLIC_KEY", "")
    private_key = os.getenv("ATLAS_PRIVATE_KEY", "")

    if not project_id or not public_key or not private_key:
        logger.error(
            "Missing Atlas Admin API credentials. Please set ATLAS_PROJECT_ID, "
            "ATLAS_PUBLIC_KEY, and ATLAS_PRIVATE_KEY environment variables."
        )
        return 1

    # 1. Discover or use provided IP
    raw_ip = args.ip
    if not raw_ip:
        try:
            raw_ip = fetch_public_ip()
        except Exception as exc:
            logger.error("IP discovery failed: %s", exc)
            return 1

    try:
        cidr_32 = to_cidr_32(raw_ip)
    except InvalidIPAddressError as err:
        logger.error("IP validation failed: %s", err)
        return 1

    # 2. Generate unique comment
    comment = generate_run_comment(
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )

    manager = AtlasAccessListManager(
        project_id=project_id,
        public_key=public_key,
        private_key=private_key,
        base_url=args.base_url,
    )

    # 3. Create entry with deleteAfterDate
    try:
        result = manager.create_access_list_entry(
            cidr_or_ip=cidr_32,
            comment=comment,
            duration_seconds=args.duration,
        )
    except AtlasAuthError as err:
        logger.error("Authentication/Authorization error: %s", err)
        return 1
    except AtlasAPIError as err:
        logger.error("Failed to create Atlas access list entry: %s", err)
        return 1

    created_by_run = result.get("created_by_this_run", True)
    delete_after = result.get("deleteAfterDate")

    # 4. Save state file
    state_data = {
        "cidr": cidr_32,
        "comment": comment,
        "created_by_run": created_by_run,
        "delete_after_date": delete_after,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_state(args.state_file, state_data)

    # 5. Wait for propagation if requested
    if args.wait_propagation and created_by_run:
        try:
            manager.wait_for_propagation(cidr_32)
        except AtlasPropagationTimeoutError as err:
            logger.warning("Propagation wait timed out: %s. Proceeding to test connectivity...", err)
        except AtlasAPIError as err:
            logger.error("Propagation error: %s", err)
            return 1

    logger.info("Successfully configured temporary Atlas access for %s", cidr_32)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Execute MongoDB connectivity check."""
    success = verify_mongodb_connectivity(timeout_ms=args.timeout * 1000)
    if success:
        logger.info("Database connectivity check PASSED.")
        return 0
    else:
        logger.error("Database connectivity check FAILED.")
        return 1


def cmd_delete(args: argparse.Namespace) -> int:
    """Execute cleanup flow."""
    project_id = os.getenv("ATLAS_PROJECT_ID", "")
    public_key = os.getenv("ATLAS_PUBLIC_KEY", "")
    private_key = os.getenv("ATLAS_PRIVATE_KEY", "")

    if not project_id or not public_key or not private_key:
        logger.error(
            "Missing Atlas credentials for cleanup. Set ATLAS_PROJECT_ID, "
            "ATLAS_PUBLIC_KEY, and ATLAS_PRIVATE_KEY."
        )
        return 1

    manager = AtlasAccessListManager(
        project_id=project_id,
        public_key=public_key,
        private_key=private_key,
        base_url=args.base_url,
    )

    cidr = args.cidr
    comment = args.comment
    created_by_run = True
    delete_after_date = None

    # 1. First, attempt to load from local state file
    state = load_state(args.state_file)
    if state:
        cidr = cidr or state.get("cidr")
        comment = comment or state.get("comment")
        created_by_run = state.get("created_by_run", True)
        delete_after_date = state.get("delete_after_date")

    # 2. If state file is missing or lacks CIDR, attempt recovery using run_id / run_attempt
    if not cidr:
        target_comment = comment
        run_id = getattr(args, "run_id", None) or os.getenv("GITHUB_RUN_ID")
        run_attempt = getattr(args, "run_attempt", None) or os.getenv("GITHUB_RUN_ATTEMPT", "1")

        if not target_comment and run_id:
            target_comment = generate_run_comment(
                run_id=run_id,
                run_attempt=run_attempt,
            )

        if target_comment:
            logger.info(
                "Local state file not found. Searching Atlas for entry created by this run with comment '%s'...",
                target_comment,
            )
            try:
                matched_entry = manager.find_entry_by_comment(target_comment)
                if matched_entry:
                    matched_cidr = matched_entry.get("cidrBlock")
                    if not matched_cidr and "ipAddress" in matched_entry:
                        matched_cidr = f"{matched_entry['ipAddress']}/32"

                    if matched_cidr:
                        # Verify the recovered entry is a valid single-host /32
                        try:
                            cidr = to_cidr_32(matched_cidr)
                        except InvalidIPAddressError as err:
                            logger.error(
                                "Recovered entry %s failed single-host /32 validation: %s. "
                                "Aborting deletion to avoid removing invalid or non-host ranges.",
                                matched_cidr,
                                err,
                            )
                            return 1

                        comment = target_comment
                        created_by_run = True
                        delete_after_date = matched_entry.get("deleteAfterDate")
                        logger.info(
                            "RECOVERY SUCCESS: Located Atlas entry matching comment '%s': %s (deleteAfterDate=%s)",
                            target_comment,
                            cidr,
                            delete_after_date,
                        )
                else:
                    logger.info(
                        "No Atlas access list entry found matching comment '%s'. "
                        "The entry was either already deleted, expired, or never created. Nothing to delete.",
                        target_comment,
                    )
                    return 0
            except AtlasAPIError as err:
                logger.error(
                    "Error querying Atlas access list during comment-based cleanup recovery: %s. "
                    "Safely falling back to Atlas automatic one-hour expiry.",
                    err,
                )
                return 1

    if not cidr:
        logger.info(
            "Neither local state file nor verifiable run identifier found. "
            "Safely falling back to Atlas automatic one-hour expiry to prevent deleting unverified rules."
        )
        return 0

    # 3. If entry was shared or not created by this run, do not delete
    if not created_by_run and not args.force:
        logger.info(
            "Entry %s was shared/pre-existing when this run started. "
            "Skipping cleanup to avoid disrupting other services.",
            cidr,
        )
        clear_state(args.state_file)
        return 0

    # 4. Strict safety check: Never delete without comment verification unless --force
    if not comment and not args.force:
        logger.warning(
            "SAFETY CHECK ABORT: Cannot verify ownership for %s without comment. "
            "Never deleting entry based only on IP address. Relying on Atlas automatic expiry (%s).",
            cidr,
            delete_after_date or "1 hour",
        )
        clear_state(args.state_file)
        return 0

    try:
        deleted = manager.delete_access_list_entry(
            cidr_or_ip=cidr,
            expected_comment=comment if not args.force else None,
        )
        if deleted:
            logger.info("Cleanup completed successfully for %s", cidr)
            clear_state(args.state_file)
            return 0
        else:
            logger.warning(
                "Cleanup skipped: comment mismatch for %s. Relying on Atlas automatic expiry (%s).",
                cidr,
                delete_after_date or "1 hour",
            )
            clear_state(args.state_file)
            return 0
    except AtlasAPIError as err:
        logger.error(
            "Cleanup API failed: %s. NOTE: Atlas automatic expiry (deleteAfterDate=%s) "
            "will remove the entry automatically.",
            err,
            delete_after_date or "1 hour",
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="MongoDB Atlas Temporary IP Allowlisting Tool for CI/CD runners."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_ATLAS_BASE_URL,
        help="MongoDB Atlas Admin API base URL",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # 'add' command
    parser_add = subparsers.add_parser("add", help="Add runner public IP to Atlas allowlist")
    parser_add.add_argument("--ip", help="Explicit public IP (otherwise auto-discovered)")
    parser_add.add_argument("--run-id", help="GitHub run ID for comment tracking")
    parser_add.add_argument("--run-attempt", help="GitHub run attempt for comment tracking")
    parser_add.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="Access duration in seconds before automatic expiry (default: 3600 = 1 hour)",
    )
    parser_add.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="Path to store state for cleanup step",
    )
    parser_add.add_argument(
        "--wait-propagation",
        action="store_true",
        default=True,
        help="Poll Atlas status until ACTIVE before returning (default: True)",
    )
    parser_add.add_argument(
        "--no-wait",
        dest="wait_propagation",
        action="store_false",
        help="Do not wait for propagation",
    )

    # 'verify' command
    parser_verify = subparsers.add_parser("verify", help="Verify MongoDB database connectivity")
    parser_verify.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Timeout in seconds for database ping (default: 10)",
    )

    # 'delete' command
    parser_del = subparsers.add_parser("delete", help="Safely delete runner IP from Atlas allowlist")
    parser_del.add_argument("--cidr", help="CIDR or IP to delete (otherwise read from state file)")
    parser_del.add_argument(
        "--comment",
        help="Expected comment for safety check (otherwise read from state file)",
    )
    parser_del.add_argument("--run-id", help="GitHub run ID for comment tracking recovery")
    parser_del.add_argument("--run-attempt", help="GitHub run attempt for comment tracking recovery")
    parser_del.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="Path to state file",
    )
    parser_del.add_argument(
        "--force",
        action="store_true",
        help="Bypass comment safety check (caution)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.action == "add":
        return cmd_add(args)
    elif args.action == "verify":
        return cmd_verify(args)
    elif args.action == "delete":
        return cmd_delete(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
