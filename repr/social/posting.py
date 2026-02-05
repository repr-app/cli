"""
Post to social platforms.

Handles the actual posting to Twitter, LinkedIn, etc.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

from .models import (
    SocialPlatform,
    SocialDraft,
    DraftStatus,
)
from .db import get_social_db
from .oauth import refresh_token_if_needed, get_connection_status


class PostingError(Exception):
    """Error during posting."""
    pass


async def post_to_twitter(
    draft: SocialDraft,
    access_token: str,
) -> Dict[str, Any]:
    """
    Post to Twitter/X.
    
    Handles both single tweets and threads.
    """
    async with httpx.AsyncClient() as client:
        # Post first tweet
        response = await client.post(
            "https://api.twitter.com/2/tweets",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"text": draft.content},
        )
        
        if response.status_code != 201:
            error = response.json()
            raise PostingError(f"Twitter API error: {error}")
        
        data = response.json().get("data", {})
        tweet_id = data.get("id")
        tweet_ids = [tweet_id]
        
        # Post thread parts if present
        if draft.thread_parts:
            reply_to_id = tweet_id
            for part in draft.thread_parts:
                response = await client.post(
                    "https://api.twitter.com/2/tweets",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": part,
                        "reply": {"in_reply_to_tweet_id": reply_to_id},
                    },
                )
                if response.status_code == 201:
                    reply_data = response.json().get("data", {})
                    reply_to_id = reply_data.get("id")
                    tweet_ids.append(reply_to_id)
        
        # Get username for URL
        user_response = await client.get(
            "https://api.twitter.com/2/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        username = "user"
        if user_response.status_code == 200:
            username = user_response.json().get("data", {}).get("username", "user")
        
        return {
            "post_id": tweet_id,
            "post_url": f"https://twitter.com/{username}/status/{tweet_id}",
            "thread_ids": tweet_ids if len(tweet_ids) > 1 else None,
        }


async def post_to_linkedin(
    draft: SocialDraft,
    access_token: str,
) -> Dict[str, Any]:
    """
    Post to LinkedIn.
    """
    async with httpx.AsyncClient() as client:
        # First get the user URN
        me_response = await client.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me_response.status_code != 200:
            raise PostingError(f"Failed to get LinkedIn user: {me_response.text}")
        
        user_id = me_response.json().get("id")
        user_urn = f"urn:li:person:{user_id}"
        
        # Create the post
        post_data = {
            "author": user_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": draft.content,
                    },
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }
        
        response = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=post_data,
        )
        
        if response.status_code not in [200, 201]:
            error = response.text
            raise PostingError(f"LinkedIn API error: {error}")
        
        # LinkedIn returns the post URN in the header
        post_urn = response.headers.get("x-restli-id", "")
        post_id = post_urn.split(":")[-1] if post_urn else None
        
        return {
            "post_id": post_id,
            "post_url": f"https://www.linkedin.com/feed/update/{post_urn}" if post_urn else None,
        }


async def post_draft(
    draft_id: str,
    platform: Optional[SocialPlatform] = None,
) -> Dict[str, Any]:
    """
    Post a draft to its platform.
    
    Args:
        draft_id: ID of the draft to post
        platform: Override platform (uses draft's platform if not specified)
    
    Returns:
        Result dict with post_id, post_url, etc.
    """
    db = get_social_db()
    draft = db.get_draft(draft_id)
    
    if not draft:
        raise PostingError(f"Draft not found: {draft_id}")
    
    if draft.status == DraftStatus.POSTED:
        raise PostingError("Draft already posted")
    
    target_platform = platform or draft.platform
    
    # Check connection
    conn_status = get_connection_status(target_platform)
    if not conn_status.get("connected"):
        raise PostingError(f"Not connected to {target_platform.value}")
    
    # Get/refresh token
    access_token = await refresh_token_if_needed(target_platform)
    if not access_token:
        raise PostingError(f"Failed to get access token for {target_platform.value}")
    
    # Post based on platform
    try:
        if target_platform == SocialPlatform.TWITTER:
            result = await post_to_twitter(draft, access_token)
        elif target_platform == SocialPlatform.LINKEDIN:
            result = await post_to_linkedin(draft, access_token)
        else:
            raise PostingError(f"Posting to {target_platform.value} not yet implemented")
        
        # Update draft status
        db.update_draft_status(
            draft_id,
            DraftStatus.POSTED,
            post_id=result.get("post_id"),
            post_url=result.get("post_url"),
        )
        
        return {
            "success": True,
            "draft_id": draft_id,
            "platform": target_platform.value,
            **result,
        }
        
    except Exception as e:
        # Update draft with error
        db.update_draft_status(
            draft_id,
            DraftStatus.FAILED,
            error_message=str(e),
        )
        raise PostingError(str(e))


def post_draft_sync(draft_id: str, platform: Optional[SocialPlatform] = None) -> Dict[str, Any]:
    """Synchronous wrapper for post_draft."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(post_draft(draft_id, platform))
    finally:
        loop.close()


async def post_multiple_drafts(
    draft_ids: List[str],
    delay_seconds: int = 60,
) -> List[Dict[str, Any]]:
    """
    Post multiple drafts with a delay between each.
    
    Args:
        draft_ids: List of draft IDs to post
        delay_seconds: Seconds to wait between posts
    
    Returns:
        List of results for each draft
    """
    results = []
    
    for i, draft_id in enumerate(draft_ids):
        try:
            result = await post_draft(draft_id)
            results.append(result)
        except PostingError as e:
            results.append({
                "success": False,
                "draft_id": draft_id,
                "error": str(e),
            })
        
        # Wait before next post (except for last one)
        if i < len(draft_ids) - 1:
            await asyncio.sleep(delay_seconds)
    
    return results


# Note: Reddit and HN posting would require their own authentication
# and API integrations. For now, these platforms are copy-to-clipboard only.

async def copy_to_clipboard(draft: SocialDraft) -> str:
    """
    Format draft for clipboard copy (for platforms without API).
    """
    if draft.platform in [SocialPlatform.REDDIT, SocialPlatform.HACKERNEWS, SocialPlatform.INDIEHACKERS]:
        parts = []
        if draft.title:
            parts.append(f"Title: {draft.title}")
            parts.append("")
        parts.append(draft.content or "")
        if draft.subreddit:
            parts.append("")
            parts.append(f"Subreddit: r/{draft.subreddit}")
        return "\n".join(parts)
    
    return draft.content or ""
