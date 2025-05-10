import random
import time
from functools import wraps

def exponential_backoff_retry(base_backoff=0.5, max_retries=5, exceptions=(Exception,) ):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries >= max_retries:
                        '''
                        Greater than or equals (>=) ensures if by max_retries = 0 then also
                        the loop breaks after single try
                        '''
                        raise
                    wait_time = base_backoff * (2 ** (retries - 1))
                    jitter = random.uniform(0, wait_time) # Full Jitter
                    time.sleep(jitter)
        return wrapper
    return decorator