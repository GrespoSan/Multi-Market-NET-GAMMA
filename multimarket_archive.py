"""Supabase archive backend intentionally disabled in V2.

The previous experimental implementation has no active network pathway.
V2 encrypted snapshots use GitHub Actions artifacts instead.
"""
class PrivateArchive:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Multi-Market V2: accesso a Supabase disattivato.")


def read_archive_config(config):
    """Always return None; do not read or forward any credentials."""
    return None
