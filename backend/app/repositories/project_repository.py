import secrets

from backend.core.security import hash_secret, sdk_key
from backend.core.settings import settings
from backend.database.postgresql import PostgresStore


class ProjectRepository:
    def __init__(self) -> None:
        self.store = PostgresStore(settings.metrics_database)

    def list_for_user(self, user_id: str) -> list[dict]:
        return self.store.fetch_all(
            """
            SELECT project_id, project_name, description, tenant_id, sdk_key_preview, sdk_key_name,
                   created_at, updated_at
            FROM dashboard_projects
            WHERE owner_user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )

    def get_for_user(self, project_id: str, user_id: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT project_id, project_name, description, tenant_id, sdk_key_preview, sdk_key_name,
                   created_at, updated_at
            FROM dashboard_projects
            WHERE project_id = %s AND owner_user_id = %s
            LIMIT 1
            """,
            (project_id, user_id),
        )

    def create(self, user_id: str, project_name: str, description: str | None) -> dict:
        project_id = f"proj_{secrets.token_hex(8)}"
        tenant_id = f"tenant_{user_id.replace('user_', '')}"
        self.store.execute(
            """
            INSERT INTO dashboard_projects (
                project_id, owner_user_id, project_name, description,
                tenant_id
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                project_id,
                user_id,
                project_name,
                description,
                tenant_id,
            ),
        )
        self.sync_metrics_project(project_id, project_name)
        return self.get_by_id(project_id)

    def regenerate_key(self, project_id: str, user_id: str, key_name: str | None = None) -> dict:
        project = self.get_for_user(project_id, user_id)
        if not project or "error" in project:
            return {}
        key = sdk_key(settings.sdk_key_prefix, project_id)
        clean_name = (key_name or "default-sdk").strip() or "default-sdk"
        self.store.execute(
            """
            UPDATE dashboard_projects
            SET sdk_key_hash = %s, sdk_key_preview = %s, sdk_key_name = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND owner_user_id = %s
            """,
            (hash_secret(key), key[-12:], clean_name, project_id, user_id),
        )
        updated = self.get_for_user(project_id, user_id)
        updated["sdk_key"] = key
        return updated

    def get_by_id(self, project_id: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT project_id, project_name, description, tenant_id, sdk_key_preview, sdk_key_name,
                   created_at, updated_at
            FROM dashboard_projects
            WHERE project_id = %s
            LIMIT 1
            """,
            (project_id,),
        )

    def sync_metrics_project(self, project_id: str, project_name: str) -> None:
        self.store.execute(
            """
            INSERT INTO projects (project_id, project_name)
            VALUES (%s, %s)
            ON CONFLICT (project_id) DO UPDATE SET project_name = EXCLUDED.project_name
            """,
            (project_id, project_name),
        )

    def get_by_sdk_key(self, key: str) -> dict:
        return self.store.fetch_one(
            """
            SELECT project_id, project_name, tenant_id
            FROM dashboard_projects
            WHERE sdk_key_hash = %s
            LIMIT 1
            """,
            (hash_secret(key),),
        )

