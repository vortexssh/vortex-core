"""Resolve the real client IP behind reverse proxies."""


def extract_client_ip(
    *,
    host: str | None,
    forwarded_for: str | None,
    real_ip: str | None = None,
) -> str | None:
    """Prefer X-Forwarded-For (first hop) then X-Real-IP, then socket peer."""
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        if candidate:
            return candidate
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return host


def websocket_client_ip(websocket) -> str | None:
    headers = websocket.headers
    forwarded = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    real_ip = headers.get("x-real-ip") or headers.get("X-Real-IP")
    peer = websocket.client.host if websocket.client else None
    return extract_client_ip(host=peer, forwarded_for=forwarded, real_ip=real_ip)
