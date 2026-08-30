"""Validate managed Supabase sessions; local mode is loopback-only."""

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str


def hosted_environment() -> bool:
    return os.getenv("CHESSLAB_ENV") == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT_ID") or os.getenv("DATABASE_URL"))


def auth_mode() -> str:
    return os.getenv("CHESSLAB_AUTH_MODE", "supabase" if hosted_environment() else "local")


def validate_auth_configuration() -> None:
    mode = auth_mode()
    if mode not in {"local", "supabase"}:
        raise RuntimeError("CHESSLAB_AUTH_MODE must be local or supabase.")
    if mode == "local":
        if hosted_environment():
            raise RuntimeError("Local authentication is forbidden in production.")
        return
    url = urlparse(os.getenv("SUPABASE_URL", ""))
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise RuntimeError("Set SUPABASE_URL to the HTTPS project URL.")
    if not os.getenv("SUPABASE_PUBLISHABLE_KEY"):
        raise RuntimeError("Set SUPABASE_PUBLISHABLE_KEY (not a service-role key).")
    if hosted_environment() and not os.getenv("CHESSLAB_ALLOWED_EMAILS", "").strip():
        raise RuntimeError("Set CHESSLAB_ALLOWED_EMAILS for the invite-only beta.")


@lru_cache(maxsize=1)
def auth_client() -> httpx.Client:
    return httpx.Client(timeout=8, follow_redirects=False)


def get_principal(request: Request) -> Principal | None:
    if auth_mode() == "local":
        # A local bypass is never selected from a request header or cookie.
        if (hosted_environment() or not request.client or request.client.host not in {"127.0.0.1", "::1"}
                or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or any(header in request.headers for header in ("forwarded", "x-forwarded-for", "x-forwarded-host"))):
            raise HTTPException(403, "Local mode only accepts direct loopback requests.")
        return None
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 16384:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    try:
        response = auth_client().get(
            os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/user",
            headers={"Authorization": authorization, "apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]},
        )
    except httpx.HTTPError as error:
        raise HTTPException(503, "Sign-in verification is temporarily unavailable.") from error
    if response.status_code in {401, 403}:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    if response.status_code != 200:
        raise HTTPException(503, "Sign-in verification is temporarily unavailable.")
    try:
        user = response.json()
        subject = str(UUID(user["id"]))
        email = user["email"].strip().casefold()
        if not user.get("email_confirmed_at") or user.get("is_anonymous") or not email:
            raise ValueError("Unverified identity")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise HTTPException(401, "A verified account is required.") from error
    allowed = {email.strip().casefold() for email in os.getenv("CHESSLAB_ALLOWED_EMAILS", "").split(",") if email.strip()}
    if allowed and email not in allowed:
        raise HTTPException(403, "This beta is invite-only. Ask Kevin to add your Google email.")
    return Principal(subject, email)
