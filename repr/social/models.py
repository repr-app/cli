"""
Data models for social posts feature.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class SocialPlatform(str, Enum):
    """Supported social platforms."""
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    INDIEHACKERS = "indiehackers"


class ConnectionStatus(str, Enum):
    """OAuth connection status."""
    DISCONNECTED = "disconnected"
    PENDING = "pending"
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


class DraftStatus(str, Enum):
    """Status of a social draft."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"


class PlatformConfig(BaseModel):
    """Platform-specific configuration and constraints."""
    platform: SocialPlatform
    max_length: int = Field(description="Maximum character length for main content")
    supports_threads: bool = Field(default=False)
    supports_media: bool = Field(default=True)
    requires_title: bool = Field(default=False)
    title_max_length: Optional[int] = None
    supports_url: bool = Field(default=True)
    tone: str = Field(default="neutral", description="Recommended tone: casual, professional, technical")

    @classmethod
    def twitter(cls) -> "PlatformConfig":
        return cls(
            platform=SocialPlatform.TWITTER,
            max_length=280,
            supports_threads=True,
            supports_media=True,
            requires_title=False,
            tone="casual",
        )

    @classmethod
    def linkedin(cls) -> "PlatformConfig":
        return cls(
            platform=SocialPlatform.LINKEDIN,
            max_length=3000,
            supports_threads=False,
            supports_media=True,
            requires_title=False,
            tone="professional",
        )

    @classmethod
    def reddit(cls) -> "PlatformConfig":
        return cls(
            platform=SocialPlatform.REDDIT,
            max_length=40000,
            supports_threads=False,
            supports_media=True,
            requires_title=True,
            title_max_length=300,
            tone="casual",
        )

    @classmethod
    def hackernews(cls) -> "PlatformConfig":
        return cls(
            platform=SocialPlatform.HACKERNEWS,
            max_length=2000,
            supports_threads=False,
            supports_media=False,
            requires_title=True,
            title_max_length=80,
            supports_url=True,
            tone="technical",
        )

    @classmethod
    def indiehackers(cls) -> "PlatformConfig":
        return cls(
            platform=SocialPlatform.INDIEHACKERS,
            max_length=10000,
            supports_threads=False,
            supports_media=True,
            requires_title=True,
            title_max_length=100,
            tone="casual",
        )


class SocialDraft(BaseModel):
    """A draft social post ready for review/posting."""
    id: str = Field(description="Unique draft ID (ULID)")
    platform: SocialPlatform
    story_id: Optional[str] = Field(default=None, description="Source story ID if generated from story")
    
    # Content
    title: Optional[str] = Field(default=None, description="Title for platforms that require it")
    content: str = Field(description="Main post content")
    thread_parts: Optional[List[str]] = Field(default=None, description="Thread parts for Twitter")
    url: Optional[str] = Field(default=None, description="URL to include")
    
    # Reddit-specific
    subreddit: Optional[str] = Field(default=None, description="Target subreddit")
    
    # Status and timestamps
    status: DraftStatus = Field(default=DraftStatus.DRAFT)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    posted_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    
    # Metadata
    post_id: Optional[str] = Field(default=None, description="ID from platform after posting")
    post_url: Optional[str] = Field(default=None, description="URL of posted content")
    error_message: Optional[str] = None
    
    # Generation metadata
    generation_prompt: Optional[str] = Field(default=None, description="Prompt used to generate this draft")
    auto_generated: bool = Field(default=True, description="Whether this was auto-generated")

    class Config:
        use_enum_values = True


class SocialConnection(BaseModel):
    """OAuth connection to a social platform."""
    id: str = Field(description="Unique connection ID")
    platform: SocialPlatform
    status: ConnectionStatus = Field(default=ConnectionStatus.DISCONNECTED)
    
    # OAuth tokens (stored securely)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    
    # User info
    platform_user_id: Optional[str] = None
    platform_username: Optional[str] = None
    platform_display_name: Optional[str] = None
    profile_url: Optional[str] = None
    
    # Timestamps
    connected_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    
    # Error info
    error_message: Optional[str] = None

    class Config:
        use_enum_values = True


class TwitterThread(BaseModel):
    """A Twitter thread with multiple tweets."""
    tweets: List[str] = Field(description="Individual tweet contents")
    total_chars: int = Field(description="Total character count")
    tweet_count: int = Field(description="Number of tweets in thread")


# Platform character limits and configuration
PLATFORM_CONFIGS = {
    SocialPlatform.TWITTER: PlatformConfig.twitter(),
    SocialPlatform.LINKEDIN: PlatformConfig.linkedin(),
    SocialPlatform.REDDIT: PlatformConfig.reddit(),
    SocialPlatform.HACKERNEWS: PlatformConfig.hackernews(),
    SocialPlatform.INDIEHACKERS: PlatformConfig.indiehackers(),
}


def get_platform_config(platform: SocialPlatform) -> PlatformConfig:
    """Get configuration for a platform."""
    return PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS[SocialPlatform.TWITTER])
