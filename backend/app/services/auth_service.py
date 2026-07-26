from fastapi import HTTPException

from backend.app.repositories.auth_repository import AuthRepository


class AuthService:
    def __init__(self) -> None:
        self.repository = AuthRepository()

    def signup(self, email: str, password: str, display_name: str | None) -> dict:
        normalized_email = email.strip().lower()
        if "@" not in normalized_email:
            raise HTTPException(status_code=400, detail="Valid email is required")
        existing = self.repository.find_by_email(normalized_email)
        if existing and "error" not in existing:
            raise HTTPException(status_code=409, detail="An account already exists for this email")
        user = self.repository.create_user(
            normalized_email,
            password,
            (display_name or normalized_email.split("@", 1)[0] or "AgentSRE User").strip(),
        )
        return self._session_response(user)

    def login(self, email: str, password: str) -> dict:
        row = self.repository.find_by_email(email.strip().lower())
        if not self.repository.password_matches(password, row):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = self.repository.find_by_id(row["user_id"])
        return self._session_response(user)

    def logout(self, authorization: str | None) -> dict:
        if authorization and authorization.lower().startswith("bearer "):
            self.repository.delete_session(authorization.split(" ", 1)[1].strip())
        return {"ok": True}

    def _session_response(self, user: dict) -> dict:
        session = self.repository.create_session(user["user_id"])
        return {
            "token": session["token"],
            "expires_at": session["expires_at"],
            "user": self.repository.public_user(user),
        }

