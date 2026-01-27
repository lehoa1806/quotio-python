"""Usage statistics models."""

from typing import Optional
from pydantic import BaseModel, Field


class UsageData(BaseModel):
    """Usage statistics data."""
    total_requests: Optional[int] = Field(None, alias="total_requests")
    success_count: Optional[int] = Field(None, alias="success_count")
    failure_count: Optional[int] = Field(None, alias="failure_count")
    total_tokens: Optional[int] = Field(None, alias="total_tokens")
    input_tokens: Optional[int] = Field(None, alias="input_tokens")
    output_tokens: Optional[int] = Field(None, alias="output_tokens")

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if not self.total_requests or self.total_requests == 0:
            return 0.0
        if not self.success_count:
            return 0.0
        return (self.success_count / self.total_requests) * 100


class UsageStats(BaseModel):
    """Usage statistics response."""
    usage: Optional[UsageData] = None
    failed_requests: Optional[int] = Field(None, alias="failed_requests")
