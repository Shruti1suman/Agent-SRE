from typing import Annotated

from fastapi import APIRouter, Depends, Header

from backend.app.dependencies import current_user
from backend.app.services.auth_service import AuthService
from backend.models.auth import LoginRequest, SignupRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup")
def signup(payload: SignupRequest) -> dict:
    return AuthService().signup(payload.email, payload.password, payload.display_name)


@router.post("/login")
def login(payload: LoginRequest) -> dict:
    return AuthService().login(payload.email, payload.password)


@router.post("/logout")
def logout(authorization: Annotated[str | None, Header()] = None) -> dict:
    return AuthService().logout(authorization)


@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    return {"user": user}

