"""
Error Handling Patterns Module

Provides robust error handling patterns based on SkillsMP best practices:
- Retry logic with exponential backoff
- Circuit breaker pattern
- Graceful degradation
- Contextual error logging
- Result types for error propagation
"""

import asyncio
import functools
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

from utils.logger import get_logger


T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ErrorContext:
    """Context for error tracking."""
    error_type: str
    error_message: str
    timestamp: datetime
    function_name: str
    file_path: str
    line_number: int
    stack_trace: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


@dataclass
class Result:
    """
    Result type for error propagation without exceptions.

    Based on functional programming patterns - use instead of raising exceptions.
    """
    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    error_context: Optional[ErrorContext] = None

    @staticmethod
    def ok(value: T) -> "Result[T]":
        """Create a successful result."""
        return Result(success=True, value=value)

    @staticmethod
    def fail(error: str, context: Optional[ErrorContext] = None) -> "Result[T]":
        """Create a failed result."""
        return Result(success=False, error=error, error_context=context)

    def is_success(self) -> bool:
        """Check if result is successful."""
        return self.success

    def is_failure(self) -> bool:
        """Check if result is failure."""
        return not self.success

    def get_or_default(self, default: T) -> T:
        """Get value or return default if failed."""
        return self.value if self.success else default

    def get_or_raise(self) -> T:
        """Get value or raise exception if failed."""
        if self.success:
            return self.value
        raise ValueError(self.error or "Unknown error")


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is tripped, requests fail immediately
    - HALF_OPEN: Testing if service has recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_attempts: int = 1
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before tripping
            timeout_seconds: Seconds to wait before trying again
            half_open_attempts: Number of successful attempts to close circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_attempts = half_open_attempts

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_success_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

        self.logger = get_logger("circuit_breaker")

    def is_open(self) -> bool:
        """Check if circuit is open."""
        if self.state == "OPEN":
            if self.last_failure_time:
                time_since_failure = datetime.utcnow() - self.last_failure_time
                if time_since_failure.total_seconds() >= self.timeout_seconds:
                    self.state = "HALF_OPEN"
                    self.logger.logger.info("Circuit breaker entering HALF_OPEN state")
                    return False
            return True
        return False

    def record_success(self):
        """Record a successful call."""
        self.failure_count = 0

        if self.state == "HALF_OPEN":
            self.half_open_success_count += 1
            if self.half_open_success_count >= self.half_open_attempts:
                self.state = "CLOSED"
                self.logger.logger.info("Circuit breaker closed after recovery")

    def record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.logger.logger.warning(
                "Circuit breaker opened",
                failure_count=self.failure_count
            )


class RetryConfig:
    """Configuration for retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            max_delay: Maximum delay between retries
            exponential_base: Base for exponential backoff
            jitter: Add randomness to delay to prevent thundering herd
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


async def retry_async(
    func: Callable[..., T],
    config: Optional[RetryConfig] = None,
    retry_on: Optional[List[Type[Exception]]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Result[T]:
    """
    Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        config: Retry configuration
        retry_on: List of exception types to retry on
        context: Additional context for logging

    Returns:
        Result with success/failure status
    """
    if config is None:
        config = RetryConfig()

    if retry_on is None:
        retry_on = [Exception]

    logger = get_logger("retry")

    last_exception = None
    context_str = " ".join(f"{k}={v}" for k, v in (context or {}).items())

    for attempt in range(config.max_retries + 1):
        try:
            result = await func()
            if attempt > 0:
                logger.logger.info(
                    "Retry succeeded",
                    attempt=attempt,
                    context=context_str
                )
            return Result.ok(result)

        except tuple(retry_on) as e:
            last_exception = e

            if attempt == config.max_retries:
                # Final attempt failed
                error_context = ErrorContext(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    timestamp=datetime.utcnow(),
                    function_name=func.__name__,
                    file_path=func.__code__.co_filename,
                    line_number=func.__code__.co_firstlineno
                )

                logger.logger.error(
                    "All retry attempts failed",
                    attempts=attempt + 1,
                    error=str(e),
                    context=context_str
                )

                return Result.fail(
                    f"Failed after {config.max_retries} retries: {str(e)}",
                    error_context
                )

            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )

            # Add jitter to prevent thundering herd
            if config.jitter:
                import random
                delay = delay * (0.5 + random.random())

            logger.logger.warning(
                "Retry attempt failed",
                attempt=attempt + 1,
                max_retries=config.max_retries,
                error=str(e),
                next_retry_delay=f"{delay:.2f}s",
                context=context_str
            )

            await asyncio.sleep(delay)


def with_retry(
    max_retries: int = 3,
    retry_on: Optional[List[Type[Exception]]] = None,
    base_delay: float = 1.0,
    exponential_base: float = 2.0
):
    """
    Decorator for adding retry logic to async functions.

    Args:
        max_retries: Maximum number of retry attempts
        retry_on: List of exception types to retry on
        base_delay: Initial delay in seconds
        exponential_base: Base for exponential backoff

    Example:
        @with_retry(max_retries=3, retry_on=[ConnectionError])
        async def fetch_data():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Result[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Result[T]:
            config = RetryConfig(
                max_retries=max_retries,
                base_delay=base_delay,
                exponential_base=exponential_base
            )

            result = await retry_async(
                lambda: func(*args, **kwargs),
                config=config,
                retry_on=retry_on,
                context={"function": func.__name__}
            )

            return result

        return wrapper
    return decorator


def with_circuit_breaker(
    failure_threshold: int = 5,
    timeout_seconds: int = 60
):
    """
    Decorator for adding circuit breaker to functions.

    Args:
        failure_threshold: Number of failures before opening circuit
        timeout_seconds: Seconds to wait before trying again

    Example:
        @with_circuit_breaker(failure_threshold=5, timeout_seconds=60)
        async def call_external_api():
            ...
    """
    circuit_breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        timeout_seconds=timeout_seconds
    )

    def decorator(func: Callable[..., T]) -> Callable[..., Result[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Result[T]:
            # Check if circuit is open
            if circuit_breaker.is_open():
                return Result.fail(
                    "Circuit breaker is open - service unavailable"
                )

            try:
                result = await func(*args, **kwargs)
                circuit_breaker.record_success()
                return Result.ok(result)

            except Exception as e:
                circuit_breaker.record_failure()
                return Result.fail(
                    f"Circuit breaker recorded failure: {str(e)}"
                )

        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    default_value: Any = None,
    error_logger: Optional[logging.Logger] = None,
    context: Optional[Dict[str, Any]] = None
) -> Result:
    """
    Safely execute a function and return Result type.

    Args:
        func: Function to execute
        default_value: Default value if function fails
        error_logger: Optional logger for errors
        context: Additional context for error reporting

    Returns:
        Result with success or failure
    """
    try:
        result = func()
        return Result.ok(result)

    except Exception as e:
        error_context = ErrorContext(
            error_type=type(e).__name__,
            error_message=str(e),
            timestamp=datetime.utcnow(),
            function_name=func.__name__,
            file_path=func.__code__.co_filename if hasattr(func, '__code__') else "unknown",
            line_number=func.__code__.co_firstlineno if hasattr(func, '__code__') else 0,
            additional_context=context
        )

        if error_logger:
            error_logger.error(
                f"Safe execute failed: {str(e)}",
                extra={"context": context or {}}
            )

        return Result.fail(
            str(e),
            error_context=error_context
        )


class GracefulDegradation:
    """
    Graceful degradation patterns for when services fail.

    Provides fallback strategies for when primary services are unavailable.
    """

    @staticmethod
    def cache_fallback(
        cache_key: str,
        cache_getter: Callable[[str], Optional[T]],
        fallback_func: Callable[[], T]
    ) -> Result[T]:
        """
        Try to get from cache, fall back to function if cache fails.

        Args:
            cache_key: Key for cache lookup
            cache_getter: Function to get from cache
            fallback_func: Function to call if cache fails

        Returns:
            Result with cached or fallback value
        """
        try:
            cached = cache_getter(cache_key)
            if cached is not None:
                return Result.ok(cached)
        except Exception as e:
            # Cache failed, use fallback
            pass

        try:
            result = fallback_func()
            return Result.ok(result)
        except Exception as e:
            return Result.fail(f"Both cache and fallback failed: {str(e)}")

    @staticmethod
    def multi_strategy_fallback(
        strategies: List[Callable[[], T]]
    ) -> Result[T]:
        """
        Try multiple strategies in order until one succeeds.

        Args:
            strategies: List of strategies to try in order

        Returns:
            Result from first successful strategy
        """
        last_error = None

        for i, strategy in enumerate(strategies):
            try:
                result = strategy()
                return Result.ok(result)
            except Exception as e:
                last_error = e
                continue

        return Result.fail(
            f"All {len(strategies)} strategies failed. Last error: {str(last_error)}"
        )


# Common exception types for retry
RETRYABLE_EXCEPTIONS = [
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
]


# Singleton instances
_default_retry_config = RetryConfig()
_default_circuit_breaker = CircuitBreaker()


def get_retry_config() -> RetryConfig:
    """Get default retry configuration."""
    return _default_retry_config


def get_circuit_breaker() -> CircuitBreaker:
    """Get default circuit breaker."""
    return _default_circuit_breaker
