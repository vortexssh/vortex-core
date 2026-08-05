"""Outbound HTTP helpers — prefer IPv4 (many VPS Docker bridges lack IPv6 routes)."""

from __future__ import annotations

import httpx


def outbound_client(*, timeout: float = 15.0) -> httpx.AsyncClient:
    # Binding to 0.0.0.0 forces IPv4 sockets; avoids ENETUNREACH on AAAA-only paths.
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(timeout=timeout, transport=transport)
