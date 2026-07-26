"""Access-address detection for the dual join QR (local + Tailscale).

Detection is best-effort and advisory — whatever the user saves in Settings
wins. Tailscale is found via its CLI when present (MagicDNS name preferred),
falling back to an interface in the CGNAT range 100.64.0.0/10.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import shutil
import socket
import subprocess

log = logging.getLogger(__name__)

_TS_RANGE = ipaddress.ip_network("100.64.0.0/10")


def detect_local_url(port: int) -> str | None:
    """The host's primary outbound interface address — normally the LAN IP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))  # no packets sent for UDP connect
            ip = probe.getsockname()[0]
        if ip and not ip.startswith("127."):
            return f"http://{ip}:{port}"
    except OSError:
        pass
    return None


def _tailscale_cli() -> str | None:
    for candidate in ("tailscale", "/usr/bin/tailscale", "/usr/local/bin/tailscale"):
        found = shutil.which(candidate) or (candidate if candidate.startswith("/") else None)
        if found:
            return found
    return None


def detect_tailscale_url(port: int) -> str | None:
    # Preferred: the CLI, which yields the MagicDNS name.
    cli = _tailscale_cli()
    if cli:
        try:
            out = subprocess.run(
                [cli, "status", "--json"], capture_output=True, timeout=3, text=True
            )
            if out.returncode == 0:
                status = json.loads(out.stdout)
                dns_name = (status.get("Self") or {}).get("DNSName", "").rstrip(".")
                if dns_name:
                    return f"http://{dns_name}:{port}"
                ips = (status.get("Self") or {}).get("TailscaleIPs") or []
                for ip in ips:
                    if ":" not in ip:
                        return f"http://{ip}:{port}"
        except Exception:  # CLI present but daemon down, JSON drift, etc.
            pass

    # Fallback: any interface address inside the Tailscale CGNAT range.
    try:
        cmd = ["ip", "-4", "addr"] if shutil.which("ip") else ["ifconfig"]
        out = subprocess.run(cmd, capture_output=True, timeout=3, text=True)
        for match in re.finditer(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", out.stdout):
            try:
                if ipaddress.ip_address(match.group(1)) in _TS_RANGE:
                    return f"http://{match.group(1)}:{port}"
            except ValueError:
                continue
    except Exception:
        pass
    return None
