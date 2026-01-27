"""Subscription Info models for displaying account subscription details."""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class PrivacyNotice:
    """Privacy notice information."""
    show_notice: Optional[bool] = None
    notice_text: Optional[str] = None


@dataclass
class SubscriptionTier:
    """Subscription tier information."""
    id: str
    name: str
    description: str
    privacy_notice: Optional[PrivacyNotice] = None
    is_default: Optional[bool] = None
    upgrade_subscription_uri: Optional[str] = None
    upgrade_subscription_text: Optional[str] = None
    upgrade_subscription_type: Optional[str] = None
    user_defined_cloudaicompanion_project: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubscriptionTier':
        """Create from dictionary."""
        privacy_notice = None
        if data.get("privacy_notice"):
            pn_data = data["privacy_notice"]
            if isinstance(pn_data, dict):
                privacy_notice = PrivacyNotice(
                    show_notice=pn_data.get("show_notice"),
                    notice_text=pn_data.get("notice_text"),
                )

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            privacy_notice=privacy_notice,
            is_default=data.get("is_default"),
            upgrade_subscription_uri=data.get("upgrade_subscription_uri"),
            upgrade_subscription_text=data.get("upgrade_subscription_text"),
            upgrade_subscription_type=data.get("upgrade_subscription_type"),
            user_defined_cloudaicompanion_project=data.get("user_defined_cloudaicompanion_project"),
        )


@dataclass
class SubscriptionInfo:
    """Subscription information for an account."""
    current_tier: Optional[SubscriptionTier] = None
    allowed_tiers: Optional[List[SubscriptionTier]] = None
    cloudaicompanion_project: Optional[str] = None
    gcp_managed: Optional[bool] = None
    upgrade_subscription_uri: Optional[str] = None
    paid_tier: Optional[SubscriptionTier] = None

    @property
    def effective_tier(self) -> Optional[SubscriptionTier]:
        """Get the effective tier - prioritize paidTier over currentTier."""
        return self.paid_tier or self.current_tier

    @property
    def tier_display_name(self) -> str:
        """Display name for the tier."""
        if self.effective_tier:
            return self.effective_tier.name
        return "Unknown"

    @property
    def tier_description(self) -> str:
        """Description of the tier."""
        if self.effective_tier:
            return self.effective_tier.description
        return ""

    @property
    def tier_id(self) -> str:
        """ID of the tier."""
        if self.effective_tier:
            return self.effective_tier.id
        return "unknown"

    @property
    def is_paid_tier(self) -> bool:
        """Check if this is a paid tier."""
        if not self.effective_tier:
            return False
        tier_id = self.effective_tier.id.lower()
        return "pro" in tier_id or "ultra" in tier_id

    @property
    def can_upgrade(self) -> bool:
        """Check if user can upgrade."""
        if not self.effective_tier:
            return False
        return self.effective_tier.upgrade_subscription_uri is not None

    @property
    def upgrade_url(self) -> Optional[str]:
        """Get upgrade URL if available."""
        if not self.effective_tier:
            return None
        return self.effective_tier.upgrade_subscription_uri

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubscriptionInfo':
        """Create from dictionary."""
        current_tier = None
        if data.get("current_tier"):
            if isinstance(data["current_tier"], dict):
                current_tier = SubscriptionTier.from_dict(data["current_tier"])

        allowed_tiers = None
        if data.get("allowed_tiers"):
            if isinstance(data["allowed_tiers"], list):
                allowed_tiers = [SubscriptionTier.from_dict(t) if isinstance(t, dict) else None
                                for t in data["allowed_tiers"]]
                allowed_tiers = [t for t in allowed_tiers if t is not None]

        paid_tier = None
        if data.get("paid_tier"):
            if isinstance(data["paid_tier"], dict):
                paid_tier = SubscriptionTier.from_dict(data["paid_tier"])

        return cls(
            current_tier=current_tier,
            allowed_tiers=allowed_tiers,
            cloudaicompanion_project=data.get("cloudaicompanion_project"),
            gcp_managed=data.get("gcp_managed"),
            upgrade_subscription_uri=data.get("upgrade_subscription_uri"),
            paid_tier=paid_tier,
        )
