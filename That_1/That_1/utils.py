import random
import time
from functools import wraps
from django.core.cache import caches

BASE_BACKOFF = 0.5
MAX_RETRIES = 5


def exponential_backoff_retry(base_backoff=BASE_BACKOFF, max_retries=MAX_RETRIES, exceptions=(Exception,)):
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
                        raise e
                    wait_time = base_backoff * (2 ** (retries - 1))
                    jitter = random.uniform(0, wait_time)  # Full Jitter
                    time.sleep(jitter)
        return wrapper
    return decorator


class CacheInteractor:
    def __init__(self, alias_name='default', exceptions=(Exception,), timeout=None,
                 base_backoff=BASE_BACKOFF, max_retries=MAX_RETRIES):

        self.cache = caches[alias_name]
        self.exceptions = exceptions
        self.base_backoff = base_backoff
        self.max_retries = max_retries
        self.timeout = timeout

    def __get_main_values(self, **kwargs):
        main_values = []

        for key, value in kwargs.items():
            main_value = value if value is not None else getattr(self, key)
            main_values.append(main_value)

        return main_values

    # This method raises only main_exceptions and logs self.exceptions
    def __raise_main_exception(self, current_exception, main_exceptions):
        if isinstance(current_exception, main_exceptions):
            ''' Can Log the error here'''
            raise current_exception

        if isinstance(current_exception, self.exceptions):
            ''' Can Log there are some unraised exception '''
            return False
        
        raise current_exception

    # Set methods return True or False
    def raise_retry_set(self, key, value, timeout=None, base_backoff=None, max_retries=None, exceptions=None):
        main_timeout, main_base_backoff, main_max_retries, main_exceptions = self.__get_main_values(
            timeout=timeout, base_backoff=base_backoff, max_retries=max_retries, exceptions=exceptions)

        fn = exponential_backoff_retry(
            base_backoff=main_base_backoff, max_retries=main_max_retries, exceptions=main_exceptions)(self.cache.set)

        try:
            fn(key, value, timeout=main_timeout)
            return True
        except Exception as e:
            return self.__raise_main_exception(e, main_exceptions)

    def raise_set(self, key, value, timeout=None, exceptions=None):
        main_timeout, main_exceptions = self.__get_main_values(
            timeout=timeout, exceptions=exceptions)

        try:
            self.cache.set(key, value, timeout=main_timeout)
            return True
        except Exception as e:
            return self.__raise_main_exception(e, main_exceptions)

    def retry_set(self, key, value, timeout=None, base_backoff=None, max_retries=None):
        main_timeout, main_base_backoff, main_max_retries = self.__get_main_values(
            timeout=timeout, base_backoff=base_backoff, max_retries=max_retries)

        fn = exponential_backoff_retry(
            base_backoff=main_base_backoff, max_retries=main_max_retries, exceptions=self.exceptions)(self.cache.set)

        try:
            fn(key, value, timeout=main_timeout)
            return True
        except self.exceptions as e:
            ''' Can Log the error here'''
            return False

    def set(self, key, value, timeout=None):
        main_timeout = self.__get_main_values(timeout=timeout)[0]
        try:
            self.cache.set(key, value, timeout=main_timeout)
            return True

        except self.exceptions as e:
            ''' Can Log the error here '''
            return False

    # Returns the value or None
    def retry_get(self, key, base_backoff=None, max_retries=None):
        main_base_backoff, main_max_retries = self.__get_main_values(
            base_backoff=base_backoff, max_retries=max_retries)

        fn = exponential_backoff_retry(
            base_backoff=main_base_backoff, max_retries=main_max_retries, exceptions=self.exceptions)(self.cache.get)

        try:
            return fn(key)
        except self.exceptions as e:
            ''' Can Log the error here '''
            return None


    def get(self, key):
        try:
            return self.cache.get(key)
        except self.exceptions as e:
            ''' Can Log the error here '''
            return None
        
    def delete(self, key):
        try:
            self.cache.delete(key)
            return True
        except self.exceptions as e:
            ''' Can Log the error here '''
            return False
