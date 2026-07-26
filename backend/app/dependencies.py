from typing import Annotated

from fastapi import Header, HTTPException

from backend.app.repositories.auth_repository import AuthRepository


def current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = AuthRepository().user_for_token(token)
    if not user or "error" in user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user

