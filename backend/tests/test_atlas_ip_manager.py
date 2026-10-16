"""
Automated unit and integration tests for Atlas Temporary IP Manager.
ALL HTTP and MongoDB Atlas API calls are strictly mocked. Zero live network calls.
"""

import ipaddress
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.atlas_ip_manager import (
    AtlasAccessListManager,
    AtlasAPIError,
    AtlasAuthError,
    AtlasIPManagerError,
    AtlasPropagationTimeoutError,
    InvalidIPAddressError,
    clear_state,
    cmd_add,
    cmd_delete,
    cmd_verify,
    fetch_public_ip,
    generate_run_comment,
    load_state,
    mask_secret,
    mask_uri,
    sanitize_text,
    save_state,
    to_cidr_32,
    validate_public_ipv4,
    verify_mongodb_connectivity,
)


class TestIPValidation(unittest.TestCase):
    """Test public IPv4 discovery and strict validation rules."""

    def test_valid_public_ipv4(self):
        valid_ips = [
            "52.14.20.100",
            "13.235.12.99",
            "104.26.10.228",
            "142.250.190.46",
            "1.1.1.1",
            "8.8.8.8",
        ]
        for ip in valid_ips:
            res = validate_public_ipv4(ip)
            self.assertEqual(res, ip)
            cidr = to_cidr_32(ip)
            self.assertEqual(cidr, f"{ip}/32")

    def test_reject_rfc1918_and_documentation_private_ips(self):
        private_ips = [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.1.100",
            # RFC 5737 Documentation / Test Networks
            "192.0.2.1",
            "198.51.100.42",
            "203.0.113.1",
        ]
        for ip in private_ips:
            with self.assertRaises(InvalidIPAddressError) as ctx:
                validate_public_ipv4(ip)
            self.assertIn("Private IP address", str(ctx.exception))

    def test_reject_loopback_and_link_local(self):
        bad_ips = [
            ("127.0.0.1", "Loopback"),
            ("127.1.2.3", "Loopback"),
            ("169.254.0.1", "Link-local"),
            ("169.254.169.254", "Link-local"),
        ]
        for ip, label in bad_ips:
            with self.assertRaises(InvalidIPAddressError) as ctx:
                validate_public_ipv4(ip)
            self.assertIn(label, str(ctx.exception))

    def test_reject_unspecified_and_broadcast(self):
        # 0.0.0.0 and 255.255.255.255
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("0.0.0.0")
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("255.255.255.255")

    def test_reject_multicast_and_reserved(self):
        # Multicast 224.0.0.0/4
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("224.0.0.1")
        # Reserved 240.0.0.0/4
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("240.0.0.1")

    def test_reject_cgnat(self):
        # 100.64.0.0/10
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("100.64.0.1")
        with self.assertRaises(InvalidIPAddressError):
            validate_public_ipv4("100.127.255.254")

    def test_reject_ipv6(self):
        ipv6_addresses = [
            "::1",
            "2001:db8::1",
            "fe80::1",
        ]
        for ip in ipv6_addresses:
            with self.assertRaises(InvalidIPAddressError):
                validate_public_ipv4(ip)

    def test_reject_malformed_strings(self):
        invalid_strings = [
            "",
            "   ",
            "not.an.ip.address",
            "999.999.999.999",
            "1.2.3.4.5",
            "1.2.3",
            "abc.def.ghi.jkl",
        ]
        for s in invalid_strings:
            with self.assertRaises(InvalidIPAddressError):
                validate_public_ipv4(s)


class TestIPDiscovery(unittest.TestCase):
    """Test public IP discovery with failover."""

    def test_fetch_public_ip_primary_success(self):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "52.14.20.100\n"
        session.get.return_value = mock_resp

        ip = fetch_public_ip(session=session)
        self.assertEqual(ip, "52.14.20.100")

    def test_fetch_public_ip_fallback_success(self):
        session = MagicMock()
        # First call fails, second succeeds
        resp_fail = MagicMock(status_code=500)
        resp_success = MagicMock(status_code=200, text="13.235.12.99")
        session.get.side_effect = [requests.RequestException("Timeout"), resp_success]

        ip = fetch_public_ip(session=session)
        self.assertEqual(ip, "13.235.12.99")

    def test_fetch_public_ip_all_fail(self):
        session = MagicMock()
        session.get.side_effect = requests.RequestException("Network down")

        with self.assertRaises(AtlasIPManagerError):
            fetch_public_ip(session=session)


class TestCommentGeneration(unittest.TestCase):
    """Test unique comment generation for workflow runs."""

    def test_generate_run_comment_from_env(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "987654321", "GITHUB_RUN_ATTEMPT": "2"}):
            comment = generate_run_comment()
            self.assertEqual(comment, "gh-actions-987654321-2")

    def test_generate_run_comment_explicit_args(self):
        comment = generate_run_comment(run_id="11223344", run_attempt="1")
        self.assertEqual(comment, "gh-actions-11223344-1")

    def test_generate_run_comment_manual_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            comment = generate_run_comment()
            self.assertTrue(comment.startswith("gh-actions-manual-"))
            self.assertLessEqual(len(comment), 80)


class TestAtlasAdminAPI(unittest.TestCase):
    """Test Atlas Admin API client with mocked responses."""

    def setUp(self):
        self.project_id = "507f1f77bcf86cd799439011"
        self.public_key = "abc123xy"
        self.private_key = "secret-private-key-uuid"
        self.session = MagicMock()
        self.manager = AtlasAccessListManager(
            project_id=self.project_id,
            public_key=self.public_key,
            private_key=self.private_key,
            session=self.session,
        )

    def test_auth_failure_401(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": 401, "detail": "Unauthorized"}
        self.session.post.return_value = mock_resp

        with self.assertRaises(AtlasAuthError) as ctx:
            self.manager.create_access_list_entry("198.51.100.1/32", "test-comment")
        self.assertIn("HTTP 401", str(ctx.exception))
        # Ensure private key is NOT in exception string
        self.assertNotIn(self.private_key, str(ctx.exception))

    def test_auth_failure_403(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"error": 403, "detail": "IP address not on access list"}
        self.session.post.return_value = mock_resp

        with self.assertRaises(AtlasAuthError) as ctx:
            self.manager.create_access_list_entry("198.51.100.1/32", "test-comment")
        self.assertIn("HTTP 403", str(ctx.exception))
        self.assertIn("Project Network Access Manager", str(ctx.exception))

    def test_create_access_list_entry_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "results": [{"cidrBlock": "198.51.100.1/32", "comment": "test-comment"}]
        }
        self.session.post.return_value = mock_resp

        res = self.manager.create_access_list_entry("198.51.100.1/32", "test-comment", duration_seconds=3600)
        self.assertEqual(res["status"], "created")
        self.assertTrue(res["created_by_this_run"])
        self.assertIn("deleteAfterDate", res)
        # Verify post payload
        called_args, called_kwargs = self.session.post.call_args
        payload = called_kwargs["json"]
        self.assertEqual(payload[0]["cidrBlock"], "198.51.100.1/32")
        self.assertEqual(payload[0]["comment"], "test-comment")
        self.assertTrue(payload[0]["deleteAfterDate"].endswith("Z"))

    def test_create_access_list_entry_409_conflict_same_comment(self):
        # Entry already exists with matching comment (reused)
        mock_post_resp = MagicMock(status_code=409)
        mock_get_resp = MagicMock(
            status_code=200,
            json=lambda: {
                "cidrBlock": "198.51.100.1/32",
                "comment": "gh-actions-12345-1",
                "deleteAfterDate": "2026-10-17T00:00:00Z",
            },
        )
        self.session.post.return_value = mock_post_resp
        self.session.get.return_value = mock_get_resp

        res = self.manager.create_access_list_entry("198.51.100.1/32", "gh-actions-12345-1")
        self.assertEqual(res["status"], "reused")
        self.assertTrue(res["created_by_this_run"])

    def test_create_access_list_entry_409_conflict_different_comment(self):
        # Entry already exists with different comment (e.g. permanent laptop IP or another runner)
        mock_post_resp = MagicMock(status_code=409)
        mock_get_resp = MagicMock(
            status_code=200,
            json=lambda: {
                "cidrBlock": "198.51.100.1/32",
                "comment": "permanent-admin-laptop",
                "deleteAfterDate": None,
            },
        )
        self.session.post.return_value = mock_post_resp
        self.session.get.return_value = mock_get_resp

        res = self.manager.create_access_list_entry("198.51.100.1/32", "gh-actions-12345-1")
        self.assertEqual(res["status"], "shared_conflict")
        # Must NOT be marked as created by this run, so cleanup won't delete it!
        self.assertFalse(res["created_by_this_run"])

    def test_propagation_polling_success(self):
        # Status goes PENDING -> ACTIVE
        resp_pending = MagicMock(status_code=200, json=lambda: {"status": "PENDING"})
        resp_active = MagicMock(status_code=200, json=lambda: {"status": "ACTIVE"})
        self.session.get.side_effect = [resp_pending, resp_active]

        with patch("time.sleep", return_value=None):
            active = self.manager.wait_for_propagation("198.51.100.1/32", max_retries=3)
            self.assertTrue(active)

    def test_propagation_polling_timeout(self):
        # Status stays PENDING until max retries
        resp_pending = MagicMock(status_code=200, json=lambda: {"status": "PENDING"})
        self.session.get.return_value = resp_pending

        with patch("time.sleep", return_value=None):
            with self.assertRaises(AtlasPropagationTimeoutError):
                self.manager.wait_for_propagation("198.51.100.1/32", max_retries=2)

    def test_propagation_status_failed(self):
        resp_failed = MagicMock(status_code=200, json=lambda: {"status": "FAILED"})
        self.session.get.return_value = resp_failed

        with self.assertRaises(AtlasAPIError) as ctx:
            self.manager.wait_for_propagation("198.51.100.1/32", max_retries=2)
        self.assertIn("FAILED", str(ctx.exception))

    def test_delete_entry_matching_comment_success(self):
        # Entry exists with expected comment -> calls DELETE -> verifies 404
        resp_get = MagicMock(
            status_code=200,
            json=lambda: {"cidrBlock": "198.51.100.1/32", "comment": "gh-actions-12345-1"},
        )
        resp_delete = MagicMock(status_code=204)
        resp_verify_404 = MagicMock(status_code=404)

        self.session.get.side_effect = [resp_get, resp_verify_404]
        self.session.delete.return_value = resp_delete

        deleted = self.manager.delete_access_list_entry(
            "198.51.100.1/32",
            expected_comment="gh-actions-12345-1",
        )
        self.assertTrue(deleted)
        self.session.delete.assert_called_once()

    def test_delete_entry_mismatched_comment_safety_abort(self):
        # Entry exists but comment does NOT match -> DO NOT DELETE!
        resp_get = MagicMock(
            status_code=200,
            json=lambda: {"cidrBlock": "198.51.100.1/32", "comment": "permanent-admin-laptop"},
        )
        self.session.get.return_value = resp_get

        deleted = self.manager.delete_access_list_entry(
            "198.51.100.1/32",
            expected_comment="gh-actions-12345-1",
        )
        # Must return False and NEVER call DELETE!
        self.assertFalse(deleted)
        self.session.delete.assert_not_called()

    def test_delete_entry_already_gone_404(self):
        # Entry not found in Atlas (already expired or deleted)
        resp_get_404 = MagicMock(status_code=404)
        self.session.get.return_value = resp_get_404

        deleted = self.manager.delete_access_list_entry(
            "198.51.100.1/32",
            expected_comment="gh-actions-12345-1",
        )
        self.assertTrue(deleted)
        self.session.delete.assert_not_called()

    def test_delete_entry_api_failure_raises(self):
        resp_get = MagicMock(
            status_code=200,
            json=lambda: {"cidrBlock": "198.51.100.1/32", "comment": "gh-actions-12345-1"},
        )
        resp_delete_500 = MagicMock(status_code=500, json=lambda: {"detail": "Atlas internal error"})
        self.session.get.return_value = resp_get
        self.session.delete.return_value = resp_delete_500

        with self.assertRaises(AtlasAPIError):
            self.manager.delete_access_list_entry(
                "198.51.100.1/32",
                expected_comment="gh-actions-12345-1",
            )


class TestStateManagement(unittest.TestCase):
    """Test saving, loading, and clearing runner state."""

    def test_save_load_clear_state(self):
        tmp_state = ".test_state_lifecycle.json"
        try:
            data = {
                "cidr": "203.0.113.10/32",
                "comment": "gh-actions-999-1",
                "created_by_run": True,
                "delete_after_date": "2026-10-17T00:00:00Z",
            }
            save_state(tmp_state, data)
            loaded = load_state(tmp_state)
            self.assertEqual(loaded, data)

            clear_state(tmp_state)
            self.assertFalse(os.path.exists(tmp_state))
            self.assertIsNone(load_state(tmp_state))
        finally:
            if os.path.exists(tmp_state):
                os.remove(tmp_state)


class TestMongoDBConnectivity(unittest.TestCase):
    """Test MongoDB connectivity verification with mocks."""

    @patch("pymongo.MongoClient")
    def test_verify_mongodb_connectivity_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}
        mock_client_cls.return_value = mock_client

        ok = verify_mongodb_connectivity("mongodb+srv://user:pass@cluster.mongodb.net/db")
        self.assertTrue(ok)
        mock_client.admin.command.assert_called_with("ping")

    @patch("pymongo.MongoClient")
    def test_verify_mongodb_connectivity_failure(self, mock_client_cls):
        from pymongo.errors import ServerSelectionTimeoutError

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = ServerSelectionTimeoutError("Timeout")
        mock_client_cls.return_value = mock_client

        ok = verify_mongodb_connectivity("mongodb+srv://user:pass@cluster.mongodb.net/db")
        self.assertFalse(ok)

    def test_verify_mongodb_connectivity_no_uri(self):
        with patch.dict(os.environ, {}, clear=True):
            ok = verify_mongodb_connectivity(uri=None)
            self.assertFalse(ok)


class TestSecretSanitization(unittest.TestCase):
    """Test that secrets are never leaked in logs or error messages."""

    def test_mask_secret(self):
        self.assertEqual(mask_secret(None), "[NOT SET]")
        self.assertEqual(mask_secret(""), "[NOT SET]")
        self.assertEqual(mask_secret("short"), "[REDACTED]")
        self.assertEqual(mask_secret("1234567890abcdef"), "1234...[REDACTED]...cdef")

    def test_mask_uri(self):
        raw = "mongodb+srv://admin_user:SuperSecretPassword123@cluster0.abcde.mongodb.net/techpulse_ai?retryWrites=true"
        masked = mask_uri(raw)
        self.assertNotIn("SuperSecretPassword123", masked)
        self.assertIn("CREDENTIALS_HIDDEN", masked)
        self.assertIn("cluster0.abcde.mongodb.net", masked)

    def test_sanitize_text(self):
        secret1 = "SuperSecretKey999"
        secret2 = "AtlasPrivateKey777"
        raw_msg = f"Failed to connect using key {secret1} and private {secret2} in cluster."
        clean = sanitize_text(raw_msg, [secret1, secret2])
        self.assertNotIn(secret1, clean)
        self.assertNotIn(secret2, clean)
        self.assertIn("[REDACTED]", clean)


class TestCLICommands(unittest.TestCase):
    """Test CLI commands end-to-end with mocks."""

    @patch("scripts.atlas_ip_manager.fetch_public_ip", return_value="52.14.20.100")
    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.create_access_list_entry")
    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.wait_for_propagation", return_value=True)
    def test_cmd_add_success(self, mock_wait, mock_create, mock_ip):
        mock_create.return_value = {
            "status": "created",
            "created_by_this_run": True,
            "deleteAfterDate": "2026-10-17T00:00:00Z",
        }
        test_state = ".test_cli_state.json"

        args = MagicMock(
            ip=None,
            run_id="12345",
            run_attempt="1",
            duration=3600,
            state_file=test_state,
            wait_propagation=True,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_add(args)
            self.assertEqual(exit_code, 0)
            mock_create.assert_called_once()
            mock_wait.assert_called_once()

            state = load_state(test_state)
            self.assertIsNotNone(state)
            self.assertEqual(state["cidr"], "52.14.20.100/32")

            # Clean up
            clear_state(test_state)

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry", return_value=True)
    def test_cmd_delete_success(self, mock_delete):
        test_state = ".test_cli_del_state.json"
        save_state(test_state, {
            "cidr": "52.14.20.100/32",
            "comment": "gh-actions-12345-1",
            "created_by_run": True,
        })

        args = MagicMock(
            cidr=None,
            comment=None,
            run_id=None,
            run_attempt=None,
            state_file=test_state,
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 0)
            mock_delete.assert_called_once_with(
                cidr_or_ip="52.14.20.100/32",
                expected_comment="gh-actions-12345-1",
            )
            # State file should be cleared
            self.assertIsNone(load_state(test_state))

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.find_entry_by_comment")
    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry", return_value=True)
    def test_cmd_delete_missing_state_recovery_success(self, mock_delete, mock_find):
        # State file is missing, but run-id is provided and Atlas entry is located by comment
        mock_find.return_value = {
            "cidrBlock": "52.14.20.100/32",
            "comment": "gh-actions-888-1",
            "deleteAfterDate": "2026-10-17T01:00:00Z",
        }
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="888",
            run_attempt="1",
            state_file=".nonexistent_state.json",
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 0)
            mock_find.assert_called_once_with("gh-actions-888-1")
            mock_delete.assert_called_once_with(
                cidr_or_ip="52.14.20.100/32",
                expected_comment="gh-actions-888-1",
            )

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.find_entry_by_comment", return_value=None)
    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry")
    def test_cmd_delete_missing_state_no_matching_entry(self, mock_delete, mock_find):
        # State file is missing, and Atlas has no entry matching the comment
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="999",
            run_attempt="1",
            state_file=".nonexistent_state.json",
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 0)
            mock_delete.assert_not_called()

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.find_entry_by_comment")
    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry")
    def test_cmd_delete_missing_state_invalid_cidr_abort(self, mock_delete, mock_find):
        # Recovered entry has an invalid/dangerous range (e.g. 0.0.0.0/0 or private)
        mock_find.return_value = {
            "cidrBlock": "0.0.0.0/0",
            "comment": "gh-actions-danger-1",
        }
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="danger",
            run_attempt="1",
            state_file=".nonexistent_state.json",
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 1)
            mock_delete.assert_not_called()

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry")
    def test_cmd_delete_shared_ip_conflict_skips_deletion(self, mock_delete):
        # Entry was shared/pre-existing (created_by_run = False)
        test_state = ".test_cli_shared_state.json"
        save_state(test_state, {
            "cidr": "52.14.20.100/32",
            "comment": "pre-existing-rule",
            "created_by_run": False,
        })
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="111",
            run_attempt="1",
            state_file=test_state,
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 0)
            mock_delete.assert_not_called()
            self.assertIsNone(load_state(test_state))

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry", return_value=False)
    def test_cmd_delete_comment_mismatch_safety_abort(self, mock_delete):
        # delete_access_list_entry returns False because live comment differs
        test_state = ".test_cli_mismatch_state.json"
        save_state(test_state, {
            "cidr": "52.14.20.100/32",
            "comment": "gh-actions-myrun-1",
            "created_by_run": True,
        })
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="myrun",
            run_attempt="1",
            state_file=test_state,
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 0)
            mock_delete.assert_called_once()
            self.assertIsNone(load_state(test_state))

    @patch("scripts.atlas_ip_manager.AtlasAccessListManager.delete_access_list_entry")
    def test_cmd_delete_atlas_api_failure(self, mock_delete):
        mock_delete.side_effect = AtlasAPIError("Atlas 500 Internal Error")
        test_state = ".test_cli_err_state.json"
        save_state(test_state, {
            "cidr": "52.14.20.100/32",
            "comment": "gh-actions-err-1",
            "created_by_run": True,
        })
        args = MagicMock(
            cidr=None,
            comment=None,
            run_id="err",
            run_attempt="1",
            state_file=test_state,
            force=False,
            base_url="https://cloud.mongodb.com/api/atlas/v2",
        )

        with patch.dict(os.environ, {
            "ATLAS_PROJECT_ID": "proj123",
            "ATLAS_PUBLIC_KEY": "pubkey",
            "ATLAS_PRIVATE_KEY": "privkey",
        }):
            exit_code = cmd_delete(args)
            self.assertEqual(exit_code, 1)

        clear_state(test_state)

    @patch("scripts.atlas_ip_manager.verify_mongodb_connectivity", return_value=True)
    def test_cmd_verify_success(self, mock_verify):
        args = MagicMock(timeout=5)
        exit_code = cmd_verify(args)
        self.assertEqual(exit_code, 0)


class TestWorkflowValidation(unittest.TestCase):
    """Test workflow YAML definitions for concurrency unification and safety."""

    def test_workflow_concurrency_group_unified(self):
        import yaml

        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        collect_path = os.path.join(root_dir, ".github", "workflows", "collect-digest.yml")
        send_path = os.path.join(root_dir, ".github", "workflows", "send-digest.yml")

        with open(collect_path, "r", encoding="utf-8") as f:
            collect_cfg = yaml.safe_load(f)
        with open(send_path, "r", encoding="utf-8") as f:
            send_cfg = yaml.safe_load(f)

        # Both must share the unified concurrency group
        self.assertEqual(collect_cfg["concurrency"]["group"], "techpulse-scheduled-workflows")
        self.assertEqual(send_cfg["concurrency"]["group"], "techpulse-scheduled-workflows")

        # Both must NOT cancel in progress
        self.assertFalse(collect_cfg["concurrency"]["cancel-in-progress"])
        self.assertFalse(send_cfg["concurrency"]["cancel-in-progress"])

        # Both must have delete step with --run-id and --run-attempt
        collect_steps = collect_cfg["jobs"]["collect-and-digest"]["steps"]
        collect_revoke = next(s for s in collect_steps if "Revoke" in s.get("name", ""))
        self.assertIn("--run-id", collect_revoke["run"])
        self.assertIn("--run-attempt", collect_revoke["run"])

        send_steps = send_cfg["jobs"]["dispatch-whatsapp-digest"]["steps"]
        send_revoke = next(s for s in send_steps if "Revoke" in s.get("name", ""))
        self.assertIn("--run-id", send_revoke["run"])
        self.assertIn("--run-attempt", send_revoke["run"])


if __name__ == "__main__":
    unittest.main()
