from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.dependencies import current_user
from backend.app.services.incident_chat_service import IncidentChatService


router = APIRouter(tags=["incidents"])


class IncidentChatMessage(BaseModel):
    role: str
    content: str


class IncidentChatRequest(BaseModel):
    message: str
    history: list[IncidentChatMessage] = Field(default_factory=list)


@router.post("/api/incidents/{incident_id}/ask")
def ask_incident(
    incident_id: str,
    payload: IncidentChatRequest,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    history = [item.model_dump() for item in payload.history]
    return IncidentChatService().answer(incident_id, payload.message, history, user.get("user_id"))
