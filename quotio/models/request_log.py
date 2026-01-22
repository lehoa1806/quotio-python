"""Request log models for tracking API requests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum


class RequestStatus(str, Enum):
    """Request status."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class RequestLog:
    """Log entry for an API request."""
    timestamp: datetime
    method: str  # GET, POST, etc.
    endpoint: str  # API endpoint path
    provider: Optional[str] = None
    model: Optional[str] = None
    resolved_model: Optional[str] = None
    resolved_provider: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    status_code: Optional[int] = None
    request_size: Optional[int] = None  # bytes
    response_size: Optional[int] = None  # bytes
    error_message: Optional[str] = None
    
    @property
    def status(self) -> RequestStatus:
        """Get request status."""
        if self.error_message:
            return RequestStatus.ERROR
        if self.status_code and 200 <= self.status_code < 300:
            return RequestStatus.SUCCESS
        return RequestStatus.ERROR
    
    @property
    def total_tokens(self) -> Optional[int]:
        """Total tokens (input + output)."""
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


@dataclass
class RequestStats:
    """Aggregate statistics for requests."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_ms: int = 0
    total_request_size: int = 0
    total_response_size: int = 0
    requests_by_provider: Dict[str, int] = field(default_factory=dict)
    requests_by_model: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    @property
    def average_duration_ms(self) -> float:
        """Average request duration in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_ms / self.total_requests
    
    @property
    def average_tokens_per_request(self) -> float:
        """Average tokens per request."""
        if self.total_requests == 0:
            return 0.0
        return self.total_tokens / self.total_requests
