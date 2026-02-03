"""
Structured Logging and Monitoring System

Based on SkillsMP langchain-architecture patterns:
- Request/response logging
- Token usage tracking
- Latency monitoring
- Error tracking
- Structured logs with context
- Performance metrics
"""

import json
import time
import os
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from functools import wraps
from enum import Enum
from collections import defaultdict
import threading

from utils.logger import get_logger


class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MetricType(Enum):
    """Types of metrics to track."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: str
    message: str
    context: Dict[str, Any]
    logger_name: str
    function_name: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    exception: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class PerformanceMetric:
    """Performance metric data point."""
    name: str
    value: float
    metric_type: str
    timestamp: str
    tags: Dict[str, str]
    unit: Optional[str] = None


class StructuredLogger:
    """
    Structured logger with context and performance tracking.

    Features:
    - JSON-formatted logs
    - Request/response tracking
    - Error aggregation
    - Performance metrics
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name
        """
        self.name = name
        self.base_logger = get_logger(name)
        self.context = {}

    def with_context(self, **kwargs) -> "StructuredLogger":
        """
        Add context to logger.

        Args:
            **kwargs: Context key-value pairs

        Returns:
            Self with context added
        """
        self.context.update(kwargs)
        return self

    def clear_context(self):
        """Clear all context."""
        self.context = {}

    def _log(
        self,
        level: LogLevel,
        message: str,
        **kwargs
    ):
        """
        Internal logging method.

        Args:
            level: Log level
            message: Log message
            **kwargs: Additional context
        """
        # Merge context with additional kwargs
        all_context = {**self.context, **kwargs}

        # Create log entry
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=level.value,
            message=message,
            context=all_context,
            logger_name=self.name,
            request_id=all_context.get('request_id'),
            user_id=all_context.get('user_id')
        )

        # Log using base logger
        log_func = getattr(self.base_logger.logger, level.value.lower())
        log_func(message, extra=all_context)

        # Also output JSON for machine parsing
        json_output = os.environ.get('STRUCTURED_LOGS_JSON', 'false').lower() == 'true'
        if json_output:
            print(entry.to_json())

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message."""
        if exception:
            kwargs['exception'] = str(exception)
            kwargs['exception_type'] = type(exception).__name__
            kwargs['stack_trace'] = traceback.format_exc()

        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log critical message."""
        if exception:
            kwargs['exception'] = str(exception)
            kwargs['exception_type'] = type(exception).__name__
            kwargs['stack_trace'] = traceback.format_exc()

        self._log(LogLevel.CRITICAL, message, **kwargs)


class MetricsCollector:
    """
    Collects and aggregates performance metrics.

    Tracks:
    - Request/response counts
    - Latency percentiles
    - Error rates
    - Token usage (for LLM calls)
    - Custom metrics
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.timers: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()

        self.logger = get_logger("metrics")

    def increment(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None):
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Value to increment by (default: 1)
            tags: Optional tags for dimension
        """
        with self.lock:
            key = self._make_key(name, tags)
            self.counters[key] += value

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """
        Set a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            tags: Optional tags for dimension
        """
        with self.lock:
            key = self._make_key(name, tags)
            self.gauges[key] = value

    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """
        Record a value in a histogram.

        Args:
            name: Metric name
            value: Value to record
            tags: Optional tags for dimension
        """
        with self.lock:
            key = self._make_key(name, tags)
            self.histograms[key].append(value)

            # Keep only last 1000 values to prevent memory issues
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]

    def record_timing(self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None):
        """
        Record a timing metric.

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            tags: Optional tags for dimension
        """
        with self.lock:
            key = self._make_key(name, tags)
            self.timers[key].append(duration_ms)

            # Keep only last 1000 values
            if len(self.timers[key]) > 1000:
                self.timers[key] = self.timers[key][-1000:]

    def get_percentile(self, name: str, percentile: float, tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """
        Get percentile value for a metric.

        Args:
            name: Metric name
            percentile: Percentile to compute (0-100)
            tags: Optional tags for dimension

        Returns:
            Percentile value or None if no data
        """
        with self.lock:
            key = self._make_key(name, tags)

            if key in self.timers and self.timers[key]:
                values = sorted(self.timers[key])
                index = int(len(values) * percentile / 100)
                return values[min(index, len(values) - 1)]

            if key in self.histograms and self.histograms[key]:
                values = sorted(self.histograms[key])
                index = int(len(values) * percentile / 100)
                return values[min(index, len(values) - 1)]

        return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all metrics.

        Returns:
            Dictionary with metric summaries
        """
        with self.lock:
            summary = {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "timers": {},
                "histograms": {}
            }

            # Add timer percentiles
            for key, values in self.timers.items():
                if values:
                    sorted_values = sorted(values)
                    summary["timers"][key] = {
                        "count": len(values),
                        "min": sorted_values[0],
                        "max": sorted_values[-1],
                        "mean": sum(values) / len(values),
                        "p50": sorted_values[int(len(values) * 0.5)],
                        "p95": sorted_values[int(len(values) * 0.95)],
                        "p99": sorted_values[int(len(values) * 0.99)],
                    }

            # Add histogram percentiles
            for key, values in self.histograms.items():
                if values:
                    sorted_values = sorted(values)
                    summary["histograms"][key] = {
                        "count": len(values),
                        "min": sorted_values[0],
                        "max": sorted_values[-1],
                        "mean": sum(values) / len(values),
                        "p50": sorted_values[int(len(values) * 0.5)],
                        "p95": sorted_values[int(len(values) * 0.95)],
                        "p99": sorted_values[int(len(values) * 0.99)],
                    }

        return summary

    def reset(self):
        """Reset all metrics."""
        with self.lock:
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()
            self.timers.clear()

    def _make_key(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Create a key for a metric with tags."""
        if not tags:
            return name

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"


class RequestTracker:
    """
    Track requests and responses with performance metrics.

    Based on langchain-architecture request/response tracking patterns.
    """

    def __init__(self):
        """Initialize request tracker."""
        self.logger = get_logger("request_tracker")
        self.metrics = MetricsCollector()
        self.structured_logger = StructuredLogger("request_tracker")

    def track_request(
        self,
        request_id: str,
        request_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Track an incoming request.

        Args:
            request_id: Unique request identifier
            request_type: Type of request (e.g., "orchestrator", "llm_call")
            metadata: Optional metadata about request
        """
        self.metrics.increment(
            f"{request_type}.requests.total",
            tags=(metadata or {})
        )

        self.structured_logger.info(
            f"Request started: {request_type}",
            request_id=request_id,
            request_type=request_type,
            **(metadata or {})
        )

    def track_response(
        self,
        request_id: str,
        request_type: str,
        duration_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Track a response.

        Args:
            request_id: Unique request identifier
            request_type: Type of request
            duration_ms: Request duration in milliseconds
            success: Whether request was successful
            metadata: Optional metadata about response
        """
        # Record timing
        self.metrics.record_timing(
            f"{request_type}.duration",
            duration_ms,
            tags=(metadata or {})
        )

        # Update counters
        if success:
            self.metrics.increment(
                f"{request_type}.requests.success",
                tags=(metadata or {})
            )
        else:
            self.metrics.increment(
                f"{request_type}.requests.error",
                tags=(metadata or {})
            )

        self.structured_logger.info(
            f"Request completed: {request_type}",
            request_id=request_id,
            request_type=request_type,
            duration_ms=duration_ms,
            success=success,
            **(metadata or {})
        )

    def track_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
        request_id: Optional[str] = None
    ):
        """
        Track an LLM API call.

        Args:
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            duration_ms: Call duration in milliseconds
            request_id: Optional request identifier
        """
        total_tokens = prompt_tokens + completion_tokens

        self.metrics.increment("llm.calls.total", tags={"model": model})
        self.metrics.increment("llm.tokens.prompt", prompt_tokens, tags={"model": model})
        self.metrics.increment("llm.tokens.completion", completion_tokens, tags={"model": model})
        self.metrics.increment("llm.tokens.total", total_tokens, tags={"model": model})
        self.metrics.record_timing("llm.duration", duration_ms, tags={"model": model})

        self.structured_logger.info(
            f"LLM call: {model}",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            request_id=request_id
        )


def log_execution_time(
    logger: Optional[StructuredLogger] = None,
    metric_name: Optional[str] = None
):
    """
    Decorator to log function execution time.

    Args:
        logger: Optional structured logger
        metric_name: Optional metric name for timing

    Example:
        @log_execution_time(metric_name="my_function")
        def my_function():
            ...
    """
    if logger is None:
        logger = StructuredLogger("decorator")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                logger.info(
                    f"Function executed: {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration_ms,
                    success=True
                )

                if metric_name:
                    get_metrics_collector().record_timing(metric_name, duration_ms)

                return result

            except Exception as e:
                duration_ms = (time.time() - start) * 1000

                logger.error(
                    f"Function failed: {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration_ms,
                    exception=e
                )

                if metric_name:
                    get_metrics_collector().record_timing(f"{metric_name}.error", duration_ms)

                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                logger.info(
                    f"Function executed: {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration_ms,
                    success=True
                )

                if metric_name:
                    get_metrics_collector().record_timing(metric_name, duration_ms)

                return result

            except Exception as e:
                duration_ms = (time.time() - start) * 1000

                logger.error(
                    f"Function failed: {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration_ms,
                    exception=e
                )

                if metric_name:
                    get_metrics_collector().record_timing(f"{metric_name}.error", duration_ms)

                raise

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Singleton instances
_metrics_collector: Optional[MetricsCollector] = None
_request_tracker: Optional[RequestTracker] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_request_tracker() -> RequestTracker:
    """Get the global request tracker instance."""
    global _request_tracker
    if _request_tracker is None:
        _request_tracker = RequestTracker()
    return _request_tracker


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


# Import asyncio at the end
import asyncio
