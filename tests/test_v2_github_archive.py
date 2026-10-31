"""Encrypted V2 GitHub Actions artifact browsing is read-only and authenticated."""
import io
import json
import unittest
import zipfile
from cryptography.fernet import Fernet

from v2_github_archive import (
    list_v2_artifacts, extract_encrypted_artifact, decrypt_encrypted,
    fetch_artifact_snapshot,
)

BASE = "https://api.github.com/repos/GrespoSan/Multi-Market-NET-GAMMA"


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.url = BASE
    def raise_for_status(self):
        pass
    def iter_content(self, n):
        for k in range(0, len(self.content), n):
            yield self.content[k:k+n]
    def close(self):
        pass


class FakeRequests:
    def __init__(self, json_data, zipped):
        self.mapping = {
            BASE + "/actions/artifacts?per_page=100": json_data,
            BASE + "/actions/artifacts/456/zip": zipped,
        }
    def get(self, url, **kwargs):
        return FakeResponse(self.mapping[url])


def example():
    import gzip
    key = Fernet.generate_key().decode()
    raw = gzip.compress(b'{"symbol":"GLD","data":{"options":[]}}')
    encrypted = Fernet(key.encode()).encrypt(raw)
    buff = io.BytesIO()
    name = "GLD_20261030T135000Z_1550_123456789abc.json.gz.enc"
    with zipfile.ZipFile(buff, "w") as archive:
        archive.writestr("run_status.json", "{}")
        archive.writestr(name, encrypted)
    items = json.dumps({"artifacts": [
        {"name": "v2-multi-market-456", "archive_download_url":
         BASE + "/actions/artifacts/456/zip",
         "created_at": "2026-10-30T14:00:00Z", "expired": False},
        {"name": "another-app-123", "archive_download_url":
         BASE + "/actions/artifacts/123/zip",
         "created_at": "2026-10-30T12:00:00Z", "expired": False}
    ]}).encode()
    return key, raw, encrypted, buff.getvalue(), items


class GitHubArchiveTests(unittest.TestCase):
    def test_listing_rejects_other_artifacts_and_uses_read_token(self):
        key, raw, encrypted, zip_bytes, listing = example()
        items = list_v2_artifacts("fake-token",
                                  session=FakeRequests(listing,zip_bytes))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "v2-multi-market-456")

    def test_audit_only_github_runs_are_not_presented_as_snapshots(self):
        key, raw, encrypted, zip_bytes, listing = example()
        dataset = json.loads(listing)
        dataset["artifacts"].insert(0, {
            "name": "v2-multi-market-999",
            "archive_download_url": BASE + "/actions/artifacts/999/zip",
            "created_at": "2026-10-30T23:35:00Z",
            "expired": False,
            "size_in_bytes": 324,  # Friday scheduled job: only run_status.json
        })
        dataset["artifacts"][1]["size_in_bytes"] = 1578490
        items = list_v2_artifacts(
            "fake-token", session=FakeRequests(json.dumps(dataset).encode(),
                                                 zip_bytes))
        self.assertEqual([x["name"] for x in items], ["v2-multi-market-456"])

    def test_rome_labels_delayed_chicago_capture_explicitly(self):
        from datetime import datetime, timezone
        from v2_storage_off import _late_capture
        self.assertFalse(_late_capture(
            "1550", datetime(2026, 10, 30, 13, 50, tzinfo=timezone.utc)))
        self.assertTrue(_late_capture(
            "1550", datetime(2026, 10, 30, 18, 54, tzinfo=timezone.utc)))
        self.assertTrue(_late_capture(
            "2030", datetime(2026, 10, 30, 22, 35, tzinfo=timezone.utc)))

    def test_decrypts_only_requested_market_from_zip(self):
        key, raw, encrypted, zip_bytes, listing = example()
        packed, name = fetch_artifact_snapshot(
            BASE + "/actions/artifacts/456/zip", "GLD",
            "token", key, session=FakeRequests(listing, zip_bytes))
        self.assertEqual(packed, raw)
        self.assertTrue(name.endswith(".json.gz"))
        with self.assertRaisesRegex(ValueError, "USO"):
            extract_encrypted_artifact(zip_bytes, "USO")
        with self.assertRaisesRegex(ValueError, "Chiave"):
            decrypt_encrypted(encrypted, Fernet.generate_key().decode())

    def test_external_artifact_url_is_rejected(self):
        key, raw, encrypted, zip_bytes, listing = example()
        with self.assertRaisesRegex(ValueError, "non appartenente"):
            fetch_artifact_snapshot(
                "https://example.org/actions/artifacts/456/zip",
                "GLD", "token", key, session=FakeRequests(listing,zip_bytes))


if __name__ == "__main__":
    unittest.main()
