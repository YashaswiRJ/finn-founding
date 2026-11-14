"""Who is asking. Network data is private to an investor; everything else in FINN is public market data.

- `Authorization: Bearer <token>` resolves to an investor (only a SHA-256 of the token is stored).
- With NETWORK_DEMO_MODE on (the default for the public demo), a request without a token reads the
  synthetic demo investor's network, so evaluators can try it without signing in.
"""
from fastapi import Header, HTTPException

from app.config import settings
from app.network import repo


def _resolve(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        inv = repo.investor_by_token(authorization[7:].strip())
        if not inv:
            raise HTTPException(401, "Unknown or expired token")
        return inv["id"]
    if settings.network_demo_mode and repo.investor(settings.demo_investor_id):
        return settings.demo_investor_id
    return None


def current_investor(authorization: str | None = Header(None)) -> str:
    """For network endpoints: an investor or 401."""
    owner = _resolve(authorization)
    if not owner:
        raise HTTPException(401, "Sign-in required for network data")
    return owner


def current_investor_optional(authorization: str | None = Header(None)) -> str | None:
    """For Push/Pull endpoints that merely add network hints: never blocks the request."""
    try:
        return _resolve(authorization)
    except HTTPException:
        return None
