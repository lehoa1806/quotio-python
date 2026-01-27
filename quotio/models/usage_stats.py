"""Usage Statistics models for displaying detailed usage data."""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class UsageData:
    """Usage data from the proxy API."""
    total_requests: Optional[int] = None
    success_count: Optional[int] = None
    failure_count: Optional[int] = None
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage (0-100)."""
        if not self.total_requests or self.total_requests == 0:
            return 0.0
        if not self.success_count:
            return 0.0
        return (float(self.success_count) / float(self.total_requests)) * 100.0


@dataclass
class UsageStats:
    """Usage statistics from the proxy API."""
    usage: Optional[UsageData] = None
    failed_requests: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'UsageStats':
        """Create from dictionary."""
        usage_data = None
        if data.get("usage"):
            usage_data = UsageData(
                total_requests=data["usage"].get("total_requests"),
                success_count=data["usage"].get("success_count"),
                failure_count=data["usage"].get("failure_count"),
                total_tokens=data["usage"].get("total_tokens"),
                input_tokens=data["usage"].get("input_tokens"),
                output_tokens=data["usage"].get("output_tokens"),
            )

        return cls(
            usage=usage_data,
            failed_requests=data.get("failed_requests"),
        )
