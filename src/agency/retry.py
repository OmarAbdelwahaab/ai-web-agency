"""Retry utilities with exponential backoff and jitter for network calls."""
from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator to retry a function on exception with exponential backoff."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempts = 0
            delay = base_delay
            while True:
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as e:
                    attempts += 1
                    if attempts > max_retries:
                        log.error("Function %s failed after %d retries: %s", fn.__name__, max_retries, e)
                        raise
                    sleep_time = delay * (random.uniform(0.8, 1.2) if jitter else 1.0)
                    log.warning(
                        "Attempt %d/%d for %s failed with %s. Retrying in %.2fs...",
                        attempts, max_retries, fn.__name__, e, sleep_time,
                    )
                    time.sleep(sleep_time)
                    delay = min(delay * backoff_factor, max_delay)

        return wrapper  # type: ignore

    return decorator
