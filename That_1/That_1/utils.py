from enum import Enum
import random
import time
from functools import wraps
from django.core.cache import caches
import asyncio
from typing import Optional
from .Configurations import BASE_BACKOFF, MAX_RETRIES


'''
Exponentially retries max_retries time, after getting exception in first attempt.
 e.g. if max_retries=2 then will try total 3 times (1 original + 2 retries)
'''
def exponential_backoff_retry(base_backoff=BASE_BACKOFF, max_retries=MAX_RETRIES, exceptions=(Exception,), is_async=False):
    def decorator(func):
        def retry_logic(retries, exception):
            if retries > max_retries:
                raise exception
            wait_time = base_backoff * (2 ** (retries - 1))
            jitter = random.uniform(0, wait_time)  # Full Jitter
            print(
                f"Retrying \"{func.__name__}\" due to \"{exception}\". Retry \"{retries}/{max_retries}\". Waiting for \"{jitter:.2f}\" seconds before next attempt.")
            return jitter

        # For Synchronous functions
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0

            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    wait_time = retry_logic(retries, e)
                    time.sleep(wait_time)

        # For Asynchronous functions
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            retries = 0

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    wait_time = retry_logic(retries, e)
                    await asyncio.sleep(wait_time)

        return async_wrapper if is_async else wrapper
    return decorator