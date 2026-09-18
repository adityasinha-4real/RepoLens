from pydantic import BaseModel


class HealthCheck(BaseModel):
    id: str
    label: str
    points: float
    max_points: float
    passed: bool
    detail: str


class HealthDimension(BaseModel):
    key: str
    label: str
    score: int | None  # 0-100, or None when the dimension does not apply
    applicable: bool
    checks: list[HealthCheck]
    summary: str


class HealthReport(BaseModel):
    overall: int | None
    dimensions: list[HealthDimension]
    methodology: str
