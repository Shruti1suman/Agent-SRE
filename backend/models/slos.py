from typing import Literal

from pydantic import BaseModel, Field


SloOperator = Literal["gt", "gte", "lt", "lte"]
SloSeverity = Literal["critical", "high", "warning", "info"]


class CreateSloRequest(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    metric_name: str = Field(min_length=2, max_length=100)
    operator: SloOperator
    threshold_value: float
    severity: SloSeverity = "warning"
    is_active: bool = True


class UpdateSloRequest(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=160)
    operator: SloOperator | None = None
    threshold_value: float | None = None
    severity: SloSeverity | None = None
    is_active: bool | None = None
