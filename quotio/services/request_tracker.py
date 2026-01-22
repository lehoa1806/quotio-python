"""Request tracking service for API request logging and analytics."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from ..models.request_log import RequestLog, RequestStats, RequestStatus


class RequestTracker:
    """Service for tracking API request history with persistence."""
    
    def __init__(self):
        """Initialize the request tracker."""
        self.request_history: List[RequestLog] = []
        self.stats = RequestStats()
        self.is_active = False
        self.last_error: Optional[str] = None
        
        # Storage
        self._storage_path = self._get_storage_path()
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load from disk
        self._load_from_disk()
    
    def _get_storage_path(self) -> Path:
        """Get storage file path."""
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            app_support = Path.home() / "Library" / "Application Support"
        elif system == "Windows":
            app_support = Path.home() / "AppData" / "Local"
        else:  # Linux
            app_support = Path.home() / ".local" / "share"
        
        quotio_dir = app_support / "Quotio-Python"
        quotio_dir.mkdir(parents=True, exist_ok=True)
        return quotio_dir / "request-history.json"
    
    def start(self):
        """Start tracking (called when proxy starts)."""
        self.is_active = True
        print("[RequestTracker] Started tracking")
    
    def stop(self):
        """Stop tracking (called when proxy stops)."""
        self.is_active = False
        print("[RequestTracker] Stopped tracking")
    
    def add_request(
        self,
        method: str,
        endpoint: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        resolved_model: Optional[str] = None,
        resolved_provider: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        duration_ms: Optional[int] = None,
        status_code: Optional[int] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Add a request entry."""
        entry = RequestLog(
            timestamp=datetime.now(),
            method=method,
            endpoint=endpoint,
            provider=provider,
            model=model,
            resolved_model=resolved_model,
            resolved_provider=resolved_provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            status_code=status_code,
            request_size=request_size,
            response_size=response_size,
            error_message=error_message,
        )
        
        self._add_entry(entry)
    
    def _add_entry(self, entry: RequestLog):
        """Add entry and update stats."""
        # Add to history (newest first)
        self.request_history.insert(0, entry)
        
        # Limit history size (keep last 1000 entries)
        if len(self.request_history) > 1000:
            self.request_history = self.request_history[:1000]
        
        # Update stats
        self._update_stats()
        
        # Save to disk
        self._save_to_disk()
    
    def _update_stats(self):
        """Update aggregate statistics."""
        stats = RequestStats()
        
        for entry in self.request_history:
            stats.total_requests += 1
            
            if entry.status == RequestStatus.SUCCESS:
                stats.successful_requests += 1
            else:
                stats.failed_requests += 1
            
            if entry.input_tokens:
                stats.total_input_tokens += entry.input_tokens
            if entry.output_tokens:
                stats.total_output_tokens += entry.output_tokens
            if entry.total_tokens:
                stats.total_tokens += entry.total_tokens
            if entry.duration_ms:
                stats.total_duration_ms += entry.duration_ms
            if entry.request_size:
                stats.total_request_size += entry.request_size
            if entry.response_size:
                stats.total_response_size += entry.response_size
            
            if entry.provider:
                stats.requests_by_provider[entry.provider] = stats.requests_by_provider.get(entry.provider, 0) + 1
            
            model = entry.resolved_model or entry.model
            if model:
                stats.requests_by_model[model] = stats.requests_by_model.get(model, 0) + 1
        
        self.stats = stats
    
    def clear_history(self):
        """Clear all history."""
        self.request_history = []
        self.stats = RequestStats()
        self._save_to_disk()
    
    def get_requests_for_provider(self, provider: str) -> List[RequestLog]:
        """Get requests filtered by provider."""
        return [r for r in self.request_history if r.provider == provider]
    
    def get_recent_requests(self, minutes: int = 60) -> List[RequestLog]:
        """Get requests from last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [r for r in self.request_history if r.timestamp >= cutoff]
    
    def _load_from_disk(self):
        """Load history from disk."""
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, "r") as f:
                data = json.load(f)
            
            # Load entries
            entries = []
            for entry_dict in data.get("entries", []):
                try:
                    entry = RequestLog(
                        timestamp=datetime.fromisoformat(entry_dict["timestamp"]),
                        method=entry_dict["method"],
                        endpoint=entry_dict["endpoint"],
                        provider=entry_dict.get("provider"),
                        model=entry_dict.get("model"),
                        resolved_model=entry_dict.get("resolved_model"),
                        resolved_provider=entry_dict.get("resolved_provider"),
                        input_tokens=entry_dict.get("input_tokens"),
                        output_tokens=entry_dict.get("output_tokens"),
                        duration_ms=entry_dict.get("duration_ms"),
                        status_code=entry_dict.get("status_code"),
                        request_size=entry_dict.get("request_size"),
                        response_size=entry_dict.get("response_size"),
                        error_message=entry_dict.get("error_message"),
                    )
                    entries.append(entry)
                except Exception as e:
                    print(f"[RequestTracker] Error loading entry: {e}")
                    continue
            
            self.request_history = entries
            self._update_stats()
            print(f"[RequestTracker] Loaded {len(entries)} entries from disk")
        except Exception as e:
            print(f"[RequestTracker] Error loading from disk: {e}")
            self.request_history = []
    
    def _save_to_disk(self):
        """Save history to disk."""
        try:
            # Convert entries to dict
            entries = []
            for entry in self.request_history[:1000]:  # Only save last 1000
                entry_dict = {
                    "timestamp": entry.timestamp.isoformat(),
                    "method": entry.method,
                    "endpoint": entry.endpoint,
                    "provider": entry.provider,
                    "model": entry.model,
                    "resolved_model": entry.resolved_model,
                    "resolved_provider": entry.resolved_provider,
                    "input_tokens": entry.input_tokens,
                    "output_tokens": entry.output_tokens,
                    "duration_ms": entry.duration_ms,
                    "status_code": entry.status_code,
                    "request_size": entry.request_size,
                    "response_size": entry.response_size,
                    "error_message": entry.error_message,
                }
                entries.append(entry_dict)
            
            data = {
                "entries": entries,
                "last_updated": datetime.now().isoformat(),
            }
            
            with open(self._storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[RequestTracker] Error saving to disk: {e}")
