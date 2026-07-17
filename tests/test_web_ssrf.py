"""Tests for the ``_assert_url_safe`` SSRF guard in functions/web.py."""
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.functions.web import _assert_url_safe


def _patch_resolve(addr):
    # socket.getaddrinfo returns [(family, type, proto, canonname, sockaddr)]
    return patch(
        "custom_components.venice_ai.functions.web.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", (addr, 0))],
    )


def test_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="scheme"):
        _assert_url_safe("file:///etc/passwd", allow_internal=False)


def test_rejects_missing_host():
    with pytest.raises(ValueError, match="hostname"):
        _assert_url_safe("http://", allow_internal=False)


@pytest.mark.parametrize("addr", [
    "127.0.0.1",          # loopback
    "10.0.0.5",           # RFC1918
    "192.168.1.1",        # RFC1918
    "172.16.0.1",         # RFC1918
    "169.254.169.254",    # link-local / cloud metadata
    "0.0.0.0",            # unspecified
    "224.0.0.1",          # multicast
])
def test_rejects_private_loopback_linklocal(addr):
    with _patch_resolve(addr):
        with pytest.raises(ValueError, match="non-public address"):
            _assert_url_safe("http://attacker.example/", allow_internal=False)


def test_public_address_allowed():
    with _patch_resolve("8.8.8.8"):
        _assert_url_safe("https://dns.google/", allow_internal=False)


def test_allow_internal_bypass():
    # Opt-in flag lets tools deliberately hit private addresses.
    with _patch_resolve("192.168.1.50"):
        _assert_url_safe("http://nas.local/api", allow_internal=True)


def test_unresolvable_host_rejected():
    import socket
    with patch(
        "custom_components.venice_ai.functions.web.socket.getaddrinfo",
        side_effect=socket.gaierror("nxdomain"),
    ):
        with pytest.raises(ValueError, match="Cannot resolve host"):
            _assert_url_safe("http://nonexistent.invalid/", allow_internal=False)
