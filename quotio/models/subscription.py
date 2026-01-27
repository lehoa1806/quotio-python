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
        """Create from dictionary. Handles both camelCase (API) and snake_case formats."""
        # Handle privacy_notice (snake_case) or privacyNotice (camelCase)
        privacy_notice = None
        pn_data = data.get("privacy_notice") or data.get("privacyNotice")
        if pn_data and isinstance(pn_data, dict):
            privacy_notice = PrivacyNotice(
                show_notice=pn_data.get("show_notice") or pn_data.get("showNotice"),
                notice_text=pn_data.get("notice_text") or pn_data.get("noticeText"),
            )

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            privacy_notice=privacy_notice,
            is_default=data.get("is_default") or data.get("isDefault"),
            upgrade_subscription_uri=data.get("upgrade_subscription_uri") or data.get("upgradeSubscriptionUri"),
            upgrade_subscription_text=data.get("upgrade_subscription_text") or data.get("upgradeSubscriptionText"),
            upgrade_subscription_type=data.get("upgrade_subscription_type") or data.get("upgradeSubscriptionType"),
            user_defined_cloudaicompanion_project=data.get("user_defined_cloudaicompanion_project") or data.get("userDefinedCloudaicompanionProject"),
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

    def _merge_tiers(self) -> Optional[SubscriptionTier]:
        """Merge currentTier and paidTier into a combined tier with the best information from both."""
        if not self.current_tier and not self.paid_tier:
            return None
        
        # If we have both, merge them - prioritize paidTier for name/ID, but keep currentTier info
        if self.paid_tier and self.current_tier:
            # Create a merged tier that combines both
            # Use paidTier for name/ID (what user paid for), but merge other fields
            return SubscriptionTier(
                id=self.paid_tier.id,  # Use paid tier ID
                name=self.paid_tier.name,  # Use paid tier name (e.g., "Google AI Pro")
                description=self.paid_tier.description or self.current_tier.description,
                privacy_notice=self.paid_tier.privacy_notice or self.current_tier.privacy_notice,
                is_default=self.current_tier.is_default,  # From current tier
                upgrade_subscription_uri=self.paid_tier.upgrade_subscription_uri or self.current_tier.upgrade_subscription_uri,
                upgrade_subscription_text=self.paid_tier.upgrade_subscription_text or self.current_tier.upgrade_subscription_text,
                upgrade_subscription_type=self.paid_tier.upgrade_subscription_type or self.current_tier.upgrade_subscription_type,
                user_defined_cloudaicompanion_project=self.current_tier.user_defined_cloudaicompanion_project,
            )
        
        # If only one exists, return it
        return self.paid_tier or self.current_tier

    @property
    def effective_tier(self) -> Optional[SubscriptionTier]:
        """Get the effective tier - merged from currentTier and paidTier."""
        return self._merge_tiers()

    @property
    def tier_display_name(self) -> str:
        """Display name for the tier - prioritizes paidTier, falls back to currentTier."""
        # Prioritize paid tier name (what user actually paid for)
        if self.paid_tier:
            return self.paid_tier.name
        if self.current_tier:
            return self.current_tier.name
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
        """Create from dictionary. Handles both camelCase (API) and snake_case formats."""
        # Handle current_tier (snake_case) or currentTier (camelCase)
        current_tier = None
        current_tier_data = data.get("current_tier") or data.get("currentTier")
        if current_tier_data and isinstance(current_tier_data, dict):
            current_tier = SubscriptionTier.from_dict(current_tier_data)

        # Handle allowed_tiers (snake_case) or allowedTiers (camelCase)
        allowed_tiers = None
        allowed_tiers_data = data.get("allowed_tiers") or data.get("allowedTiers")
        if allowed_tiers_data and isinstance(allowed_tiers_data, list):
            allowed_tiers = [SubscriptionTier.from_dict(t) if isinstance(t, dict) else None
                            for t in allowed_tiers_data]
            allowed_tiers = [t for t in allowed_tiers if t is not None]

        # Handle paid_tier (snake_case) or paidTier (camelCase)
        paid_tier = None
        paid_tier_data = data.get("paid_tier") or data.get("paidTier")
        if paid_tier_data and isinstance(paid_tier_data, dict):
            paid_tier = SubscriptionTier.from_dict(paid_tier_data)

        return cls(
            current_tier=current_tier,
            allowed_tiers=allowed_tiers,
            cloudaicompanion_project=data.get("cloudaicompanion_project") or data.get("cloudaicompanionProject"),
            gcp_managed=data.get("gcp_managed") or data.get("gcpManaged"),
            upgrade_subscription_uri=data.get("upgrade_subscription_uri") or data.get("upgradeSubscriptionUri"),
            paid_tier=paid_tier,
        )
