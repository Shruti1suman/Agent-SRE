from typing import Annotated, Any

from fastapi import APIRouter, Body, Header

from backend.app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/v1", tags=["ingestion"])


@router.post("/executions")
def ingest_execution(
    payload: dict[str, Any] = Body(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    return IngestionService().ingest(payload, authorization)


@router.post("/executions/transform")
def transform_execution(
    payload: dict[str, Any] = Body(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    return IngestionService().transform_only(payload, authorization)
