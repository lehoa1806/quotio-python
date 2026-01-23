"""
Base quota fetcher class.

WORKFLOW OVERVIEW:
==================
This module defines the base classes for quota fetchers. Each provider
(Claude, OpenAI, Copilot, etc.) has its own fetcher class that inherits
from BaseQuotaFetcher.

ARCHITECTURE:
The quota fetching system uses a strategy pattern:
- BaseQuotaFetcher: Abstract base class defining the interface
- Provider-specific fetchers: Implement fetch_quota() and fetch_all_quotas()
- QuotaViewModel: Coordinates fetching from all providers in parallel

WORKFLOW:
1. QuotaViewModel creates fetchers for each provider
2. Calls fetch_all_quotas() on each fetcher in parallel
3. Each fetcher:
   - Gets list of accounts from auth files or direct detection
   - For each account, calls provider API or reads local data
   - Parses response and creates ProviderQuotaData objects
   - Returns dictionary mapping account_key -> ProviderQuotaData
4. QuotaViewModel merges results into provider_quotas dictionary
5. UI screens are notified and update their displays

DATA STRUCTURES:
- QuotaModel: Represents quota for a single model (e.g., "claude-3-opus")
- ProviderQuotaData: Represents quota data for an account (contains multiple models)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from ..api_client import ManagementAPIClient


@dataclass
class QuotaModel:
    """
    Quota information for a specific model.
    
    This represents the quota/usage for a single AI model within an account.
    For example, a Claude account might have multiple models: claude-3-opus,
    claude-3-sonnet, etc. Each model has its own quota.
    
    Fields:
        name: Model name/identifier
        percentage: Usage percentage (0-100), or -1 if unknown/unavailable
        limit: Total quota limit (if available)
        used: Amount used (if available)
        remaining: Amount remaining (if available)
        reset_time: ISO timestamp string indicating when quota resets (if available)
    """
    name: str
    percentage: float  # -1 for unknown/unavailable
    limit: Optional[int] = None
    used: Optional[int] = None
    remaining: Optional[int] = None
    reset_time: Optional[str] = None  # ISO timestamp string (e.g., "2026-01-30T05:47:16Z")


@dataclass
class ProviderQuotaData:
    """
    Quota data for a provider account.
    
    This represents all quota information for a single account with a provider.
    An account can have multiple models, each with its own quota.
    
    Fields:
        models: List of QuotaModel objects for this account
        account_email: Email address of the account
        account_name: Display name of the account
        last_updated: Timestamp of last update
        plan_type: Subscription plan type (e.g., "pro", "free")
        membership_type: Alias for plan_type (some providers use different field names)
        subscription_status: Current subscription status
        organization_name: Organization name for enterprise accounts
    """
    models: list[QuotaModel]
    account_email: Optional[str] = None
    account_name: Optional[str] = None
    last_updated: Optional[str] = None
    plan_type: Optional[str] = None  # e.g., "pro", "pro_student", "free" for Cursor
    membership_type: Optional[str] = None  # Alias for plan_type (Cursor uses membershipType)
    subscription_status: Optional[str] = None  # Subscription status
    organization_name: Optional[str] = None  # Organization name for platform/enterprise accounts


class BaseQuotaFetcher(ABC):
    """
    Base class for quota fetchers.
    
    This is an abstract base class that defines the interface for fetching
    quotas from AI providers. Each provider (Claude, OpenAI, Copilot, etc.)
    has its own fetcher class that inherits from this and implements the
    abstract methods.
    
    WORKFLOW:
    Subclasses must implement:
    - fetch_quota(account_key): Fetch quota for a specific account
    - fetch_all_quotas(): Fetch quotas for all accounts (default implementation
      calls fetch_quota() for each account, but can be overridden for efficiency)
    
    The fetcher uses the API client to communicate with the proxy's management
    API, which in turn communicates with provider APIs or reads local data.
    """
    
    def __init__(self, api_client: Optional[ManagementAPIClient] = None):
        """
        Initialize the fetcher.
        
        Args:
            api_client: ManagementAPIClient instance for API communication.
                       Can be None for fetchers that don't use the proxy API
                       (e.g., direct file-based fetchers).
        """
        self.api_client = api_client
        self._proxy_url: Optional[str] = None  # Proxy URL for quota fetching (if needed)
    
    def update_proxy_configuration(self, proxy_url: Optional[str] = None):
        """
        Update proxy URL for quota fetching.
        
        Some fetchers need to know the proxy URL to make requests through it.
        This is called by QuotaViewModel when proxy configuration changes.
        """
        self._proxy_url = proxy_url
    
    @abstractmethod
    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """
        Fetch quota for a specific account.
        
        This is the core method that each provider fetcher must implement.
        It should:
        1. Identify the account using account_key (email, filename, etc.)
        2. Make API call or read local data to get quota information
        3. Parse the response and create ProviderQuotaData object
        4. Return the data, or None if account not found/error
        
        Args:
            account_key: Account identifier (email, filename, etc.)
            
        Returns:
            ProviderQuotaData or None if not available
        """
        pass
    
    async def fetch_all_quotas(self) -> dict[str, ProviderQuotaData]:
        """
        Fetch quotas for all accounts.
        
        Default implementation returns empty dict. Subclasses should override
        this to fetch quotas for all accounts efficiently. This method is
        called by QuotaViewModel to get all quotas for a provider.
        
        Returns:
            Dictionary mapping account_key -> ProviderQuotaData
        """
        # Default implementation - override in subclasses
        return {}
    
    async def fetch_as_provider_quota(self) -> dict[str, ProviderQuotaData]:
        """
        Fetch quotas and return in provider quota format.
        
        This is a convenience method that calls fetch_all_quotas().
        Override if you need different behavior (e.g., different data format).
        """
        return await self.fetch_all_quotas()
