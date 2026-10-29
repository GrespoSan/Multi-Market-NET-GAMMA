"""Private Supabase Storage REST client for optional long-term Multi-Market archives.

Server-only: credentials must remain in GitHub Actions Secrets / Streamlit Secrets.
Data never goes to SPX bucket, public URL or client JS.
"""
import json
from urllib.parse import quote

import requests


class PrivateArchive:
    def __init__(self, url, key, bucket="multi-market-snapshots"):
        if not url or not key:
            raise ValueError("Configura SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.")
        self.url = url.rstrip("/")
        self.key = key
        self.bucket = bucket

    def _request(self, method, route, data=None, mime="application/json"):
        headers = {"apikey": self.key, "Authorization": "Bearer " + self.key}
        if data is not None:
            headers["Content-Type"] = mime
        resp = requests.request(method, self.url + "/storage/v1" + route,
                                headers=headers, data=data, timeout=(8, 70))
        if not resp.ok:
            raise RuntimeError(f"Supabase Storage HTTP {resp.status_code}; "
                               "verifica bucket privato e credenziali.")
        return resp.content

    def upload(self, path, payload, mime):
        return self._request("POST", "/object/"
                             + quote(self.bucket, safe="") + "/"
                             + quote(path, safe="/"), payload, mime)

    def download(self, path):
        return self._request("GET", "/object/authenticated/"
                             + quote(self.bucket, safe="") + "/"
                             + quote(path, safe="/"))

    def list(self, prefix, limit=100):
        results, offset = [], 0
        while True:
            data = json.dumps({"prefix": prefix, "limit": limit, "offset": offset,
                               "sortBy": {"column": "name", "order": "desc"}}).encode()
            batch = json.loads(self._request("POST", "/object/list/"
                                             + quote(self.bucket, safe=""), data))
            good = [x for x in batch if x.get("name") and x.get("id")]
            results.extend(good)
            if len(batch) < limit:
                return results
            offset += len(batch)


def read_archive_config(config):
    """No guessing that the SPX secrets or bucket are shared across repositories."""
    get = config.get
    url = get("SUPABASE_URL") or get("MM_SUPABASE_URL")
    key = get("SUPABASE_SERVICE_ROLE_KEY") or get("MM_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return PrivateArchive(url, key, get("MM_SUPABASE_BUCKET", "multi-market-snapshots"))
