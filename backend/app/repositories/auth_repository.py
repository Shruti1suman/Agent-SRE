from datetime import datetime, timedelta, timezone
import secrets

from backend.core.security import hash_secret, password_hash, token, verify_password
from backend.core.settings import settings
from backend.database.postgresql import PostgresStore


class AuthRepository:
    def __init__(self) -> None:
        self.store = PostgresStore(settings.metrics_database)

    def public_user(self, row: dict) -> dict:
        return {
            "user_id": row.get("user_id"),
            "email": row.get("email"),
            "display_name": row.get("display_name"),
            "created_at": row.get("created_at"),
        }

    def find_by_email(self, email: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT user_id, email, display_name, password_hash, created_at
            FROM dashboard_users
            WHERE email = %s
            LIMIT 1
            """,
            (email,),
        )

    def find_by_id(self, user_id: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT user_id, email, display_name, created_at
            FROM dashboard_users
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

    def create_user(self, email: str, password: str, display_name: str) -> dict:
        user_id = f"user_{secrets.token_hex(12)}"
        self.store.execute(
            """
            INSERT INTO dashboard_users (user_id, email, display_name, password_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, email, display_name, password_hash(password)),
        )
        return self.find_by_id(user_id)

    def create_session(self, user_id: str) -> dict:
        session_token = token(settings.session_prefix)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
        self.store.execute(
            """
            INSERT INTO dashboard_sessions (token_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (hash_secret(session_token), user_id, expires_at.replace(tzinfo=None)),
        )
        return {"token": session_token, "expires_at": expires_at.isoformat()}

    def delete_session(self, session_token: str) -> None:
        self.store.execute(
            "DELETE FROM dashboard_sessions WHERE token_hash = %s",
            (hash_secret(session_token),),
        )

    def user_for_token(self, session_token: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT u.user_id, u.email, u.display_name, u.created_at
            FROM dashboard_sessions s
            JOIN dashboard_users u ON u.user_id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > CURRENT_TIMESTAMP
            LIMIT 1
            """,
            (hash_secret(session_token),),
        )

    def password_matches(self, password: str, row: dict) -> bool:
        return bool(row) and "error" not in row and verify_password(password, row.get("password_hash") or "")

