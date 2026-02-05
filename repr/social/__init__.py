"""
Social Posts module for repr.

Generate platform-specific posts from git history and stories.
"""

from .models import (
    SocialPlatform,
    SocialDraft,
    SocialConnection,
    PlatformConfig,
)
from .generator import generate_social_drafts
from .formatters import (
    format_for_twitter,
    format_for_linkedin,
    format_for_reddit,
    format_for_hackernews,
    format_for_indiehackers,
)

__all__ = [
    "SocialPlatform",
    "SocialDraft",
    "SocialConnection",
    "PlatformConfig",
    "generate_social_drafts",
    "format_for_twitter",
    "format_for_linkedin",
    "format_for_reddit",
    "format_for_hackernews",
    "format_for_indiehackers",
]
