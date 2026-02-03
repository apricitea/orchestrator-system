"""
Availability Checker - Rate Limit Detection

Checks LLM API availability by parsing response headers for rate limit information.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx
from redis.asyncio import Redis

from config.settings import get_settings
from utils.logger import get_logger
from worker.worker_config import get_worker_config


@dataclass
class RateLimitInfo:
    """Rate limit information from API response."""
    is_rate_limited: bool = False
    requests_remaining: Optional[int] = None
    requests_limit: Optional[int] = None
    reset_time: Optional[datetime] = None
    retry_after: Optional[int] = None  # Seconds to wait
    tokens_used: Optional[int] = None
    tokens_limit: Optional[int] = None

    @property
    def wait_seconds(self) -> int:
        """Calculate seconds to wait before retry."""
        if self.retry_after:
            return self.retry_after
        if self.reset_time:
            delta = self.reset_time - datetime.utcnow()
            return max(0, int(delta.total_seconds()))
        return 60  # Default


class AvailabilityChecker:
    """
    Checks LLM API availability and rate limits.

    Uses Redis to cache rate limit state and implements exponential backoff.
    """

    def __init__(self):
        self.logger = get_logger("availability_checker")
        self.settings = get_settings()
        self.worker_config = get_worker_config()
        self._redis: Optional[Redis] = None
        self._rate_limit_state: dict = {}

        # Redis keys
        self._rate_limit_key = "worker:rate_limit"
        self._available_key = "worker:available"
        self._tokens_used_key = "worker:tokens_used"
        self._daily_token_key = "worker:daily_tokens"

    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self._redis = Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=0,
                decode_responses=True,
            )
            await self._redis.ping()
            self.logger.info("Availability checker initialized")
        except Exception as e:
            self.logger.error("Failed to connect to Redis", error=str(e))
            self._redis = None

    async def is_available(self) -> tuple[bool, str]:
        """
        Check if LLM API is available.

        Returns:
            Tuple of (is_available, reason)
        """
        # Check if we're currently rate limited
        if self._redis:
            rate_limited_until = await self._redis.get(f"{self._rate_limit_key}:until")
            if rate_limited_until:
                until = datetime.fromisoformat(rate_limited_until)
                if datetime.utcnow() < until:
                    wait_seconds = int((until - datetime.utcnow()).total_seconds())
                    return False, f"Rate limited until {until.strftime('%H:%M:%S')} ({wait_seconds}s remaining)"

        # Check daily token limit
        if self._redis:
            tokens_used = await self._redis.get(self._daily_token_key)
            if tokens_used:
                tokens_used_int = int(tokens_used)
                daily_limit = self.settings.daily_token_limit
                if tokens_used_int >= daily_limit:
                    return False, f"Daily token limit reached: {tokens_used_int}/{daily_limit}"

        return True, "Available"

    async def check_api_health(self) -> RateLimitInfo:
        """
        Check API health by making a minimal request.

        Returns:
            RateLimitInfo with current status
        """
        if not self.settings.anthropic_api_key:
            return RateLimitInfo(is_rate_limited=False)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Make a minimal API request to check rate limits
                # Use the correct Anthropic API URL
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "test"}],
                    },
                )

                return self._parse_rate_limits(response)

        except Exception as e:
            self.logger.warning("API health check failed", error=str(e))
            return RateLimitInfo(is_rate_limited=False)

    def _parse_rate_limits(self, response: httpx.Response) -> RateLimitInfo:
        """Parse rate limit headers from API response."""
        headers = response.headers

        # Anthropic-specific headers
        requests_remaining = headers.get("anthropic-ratelimit-requests-remaining")
        requests_limit = headers.get("anthropic-ratelimit-requests-limit")
        reset_time = headers.get("anthropic-ratelimit-reset")
        retry_after = headers.get("retry-after")

        # Check if rate limited (429 status)
        is_rate_limited = response.status_code == 429

        # Parse reset time
        reset_datetime: Optional[datetime] = None
        if reset_time:
            try:
                reset_datetime = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
            except:
                pass

        return RateLimitInfo(
            is_rate_limited=is_rate_limited,
            requests_remaining=int(requests_remaining) if requests_remaining else None,
            requests_limit=int(requests_limit) if requests_limit else None,
            reset_time=reset_datetime,
            retry_after=int(retry_after) if retry_after else None,
        )

    async def record_rate_limit(self, info: RateLimitInfo):
        """
        Record that we're rate limited and set retry time.

        Args:
            info: Rate limit info from API response
        """
        if not self._redis:
            return

        wait_seconds = info.wait_seconds
        until = datetime.utcnow() + timedelta(seconds=wait_seconds)

        await self._redis.setex(
            f"{self._rate_limit_key}:until",
            wait_seconds + 60,  # Add buffer
            until.isoformat(),
        )

        self.logger.warning(
            "Rate limit detected",
            wait_seconds=wait_seconds,
            until=until.isoformat(),
        )

    async def record_token_usage(self, tokens: int):
        """
        Record token usage for daily limit tracking.

        Args:
            tokens: Number of tokens used
        """
        if not self._redis:
            return

        # Get current daily usage
        current = await self._redis.incrby(self._daily_token_key, tokens)

        # Set expiry to end of day (UTC)
        now = datetime.utcnow()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        ttl_seconds = int((end_of_day - now).total_seconds())
        await self._redis.expire(self._daily_token_key, ttl_seconds)

        self.logger.info(
            "Token usage recorded",
            tokens=tokens,
            daily_total=current,
            limit=self.settings.daily_token_limit,
        )

        # Check if approaching limit
        if current >= self.settings.daily_token_limit * 0.9:
            self.logger.warning(
                "Approaching daily token limit",
                current=current,
                limit=self.settings.daily_token_limit,
                percentage=int(current / self.settings.daily_token_limit * 100),
            )

    async def wait_until_available(self, max_wait_seconds: int = 3600) -> bool:
        """
        Wait until API is available.

        Args:
            max_wait_seconds: Maximum time to wait

        Returns:
            True if available, False if timed out
        """
        waited = 0
        check_interval = 30  # Check every 30 seconds

        while waited < max_wait_seconds:
            available, reason = await self.is_available()
            if available:
                return True

            self.logger.info("Waiting for API availability", reason=reason)
            await asyncio.sleep(min(check_interval, max_wait_seconds - waited))
            waited += check_interval

        return False

    async def get_status(self) -> dict:
        """Get current availability status."""
        available, reason = await self.is_available()

        tokens_used = 0
        if self._redis:
            tokens = await self._redis.get(self._daily_token_key)
            tokens_used = int(tokens) if tokens else 0

        return {
            "available": available,
            "reason": reason,
            "daily_tokens_used": tokens_used,
            "daily_tokens_limit": self.settings.daily_token_limit,
            "daily_tokens_percentage": int(tokens_used / self.settings.daily_token_limit * 100),
        }

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# Global availability checker instance
_availability_checker: Optional[AvailabilityChecker] = None


def get_availability_checker() -> AvailabilityChecker:
    """Get the global availability checker instance."""
    global _availability_checker
    if _availability_checker is None:
        _availability_checker = AvailabilityChecker()
    return _availability_checker
