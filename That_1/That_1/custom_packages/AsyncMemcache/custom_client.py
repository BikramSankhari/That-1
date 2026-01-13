from functools import wraps, cache
import inspect
from aiomcache import FlagClient
from aiomcache.client import _GetFlagHandler, _SetFlagHandler, _T, _U
from typing import Any, Mapping, Optional, Tuple, Union
from .custom_pool import CustomPool
import asyncio
from .exceptions import ResponseTimeOut
from .exponential_backoff_retry import exponential_backoff_retry
from .Configurations import BASE_MEMCACHE_BACKOFF, MAX_MEMCACHE_RETRIES

class CustomFlagClient(FlagClient):
    def __init__(self, host: str | None, port: int = 11211, *,
                 pool_size: int = 2, pool_minsize: Optional[int] = None,
                 conn_args: Optional[Mapping[str, Any]] = None,
                 get_flag_handler: Optional[_GetFlagHandler[_T]] = None,
                 set_flag_handler: Optional[_SetFlagHandler[_T]] = None,
                 connection_timeout: float, timeout: float, tcp_keepalive: bool, tcp_nodelay: bool,
                 base_backoff, max_retries, exceptions, unix_socket):

        if not pool_minsize:
            pool_minsize = pool_size

        # Passes the extra arguments to the CustomPool
        if get_flag_handler is None:
            def get_flag_handler(conn): return conn
        self._pool = CustomPool(
            host=host, port=port, unix_socket=unix_socket, minsize=pool_minsize, maxsize=pool_size,
            conn_args=conn_args, connection_timeout=connection_timeout,
            tcp_keepalive=tcp_keepalive, tcp_nodelay=tcp_nodelay)

        self._get_flag_handler = get_flag_handler
        self._set_flag_handler = set_flag_handler
        self.timeout = timeout
        self.base_backoff = base_backoff
        self.max_retries = max_retries
        self.exceptions = exceptions
        self.retry_decorator = exponential_backoff_retry(
            base_backoff=self.base_backoff, max_retries=self.max_retries, exceptions=self.exceptions, is_async=True)

    # Raises exception if a function exceeds self.timeout
    def apply_timeout(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            except TimeoutError:
                raise ResponseTimeOut("Memcached took too long to respond")
        return wrapper

    # Suppresses self.exceptions and return None
    def _suppress(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except self.exceptions as e:
                # Can log the suppressed exception here
                return None
        return wrapper

    # Determines and return the appropriate function based on retry and suppress flags
    # The result is cached so that the function is determined only once per combination of flags
    @cache
    def get_appropriate_function(self, func_name, retry: bool, suppress: bool):
        super_function = getattr(super(), func_name)

        func = self.apply_timeout(super_function)

        if retry and suppress:
            return self._suppress(self.retry_decorator(func))

        elif retry:
            return self.retry_decorator(func)

        elif suppress:
            return self._suppress(func)

        else:
            return func

    # Responsible for running the function obtained from get_appropriate_function with proper params
    async def run_appropriate_function(self, *args, retry=False, suppress=False, **kwargs):
        func_name = inspect.currentframe().f_back.f_code.co_name

        appropriate_function = self.get_appropriate_function(
            func_name=func_name, retry=retry, suppress=suppress)

        return await appropriate_function(*args, **kwargs)

    async def get(self, key: bytes, default: Optional[_U] = None, retry=False, suppress=False) -> Optional[bytes]:
        """Gets a single value from the server.

        :param key: ``bytes``, is the key for the item being fetched
        :param default: default value if there is no value.
        :param retry: ``bool``, whether to retry on exceptions.
        :param suppress: ``bool``, whether to suppress exceptions.
        :return: ``bytes``, is the data for this specified key.
        """

        return await self.run_appropriate_function(key, default=default, retry=retry, suppress=suppress)

    async def multi_get(self, *keys: bytes, retry=False, suppress=False) -> Tuple[Union[bytes, _T, None], ...]:
        """Takes a list of keys and returns a list of values.

        :param keys: ``list`` keys for the item being fetched.
        :return: ``list`` of values for the specified keys.
        :raises:``ValidationException``, ``ClientException``,
        and socket errors
        """
        return await self.run_appropriate_function(*keys, suppress=suppress, retry=retry)

    async def set(self, key: bytes, value: bytes, *, exptime: int = 0, retry=False, suppress=False) -> bool:
        """Sets a key to a value on the server
        with an optional exptime (0 means don't auto-expire)

        :param key: ``bytes``, is the key of the item.
        :param value: ``bytes``, data to store.
        :param exptime: ``int``, is expiration time. If it's 0, the
        item never expires.
        :return: ``bool``, True in case of success.
        """
        return await self.run_appropriate_function(retry=retry, suppress=suppress, key=key, value=value, exptime=exptime)

    async def add(self, key: bytes, value: bytes, *, exptime: int = 0, retry=False, suppress=False) -> bool:
        """Store this data, but only if the server *doesn't* already
        hold data for this key.

        :param key: ``bytes``, is the key of the item.
        :param value: ``bytes``,  data to store.
        :param exptime: ``int`` is expiration time. If it's 0, the
        item never expires.
        :return: ``bool``, True in case of success.
        """
        return await self.run_appropriate_function(retry=retry, suppress=suppress, key=key, value=value, exptime=exptime, )

    async def replace(self, key: bytes, value: bytes, *, exptime: int = 0, retry=False, suppress=False) -> bool:
        """Store this data, but only if the server *does*
        already hold data for this key.

        :param key: ``bytes``, is the key of the item.
        :param value: ``bytes``,  data to store.
        :param exptime: ``int`` is expiration time. If it's 0, the
        item never expires.
        :return: ``bool``, True in case of success.
        """
        return await self.run_appropriate_function(retry=retry, suppress=suppress, key=key, value=value, exptime=exptime)

    async def delete(self, key: bytes, retry=False, suppress=False) -> bool:
        """Deletes a key/value pair from the server.

        :param key: is the key to delete.
        :return: True if case values was deleted or False to indicate
        that the item with this key was not found.
        """
        return await self.run_appropriate_function(retry=retry, suppress=suppress, key=key)

    async def flush_all(self, retry=False, suppress=False) -> bool:
        """Flushes all data from the server.

        :return: True in case of success.
        """
        return await self.run_appropriate_function(retry=retry, suppress=suppress)


# This class takes additional arguments and pass them to CustomFlagClient
class CustomClient(CustomFlagClient):
    def __init__(self, host: str | None = None, port: int = 11211, unix_socket: str | None = None,
                 *, pool_size: int = 2, pool_minsize: Optional[int] = None,
                 conn_args: Optional[Mapping[str, Any]] = None, connection_timeout: float = 5.0,
                 timeout: float = 5.0, tcp_keepalive: bool = True, tcp_nodelay: bool = True,
                 exceptions=(Exception,), base_backoff=BASE_MEMCACHE_BACKOFF, max_retries=MAX_MEMCACHE_RETRIES):

        if host is None and unix_socket is None:
            raise ValueError("Either host or unix_socket must be provided")
        
        if host is not None and unix_socket is not None:
            raise ValueError("Only one of host or unix_socket should be provided")

        super().__init__(host=host, port=port, unix_socket=unix_socket, pool_size=pool_size, pool_minsize=pool_minsize,
                         conn_args=conn_args,
                         get_flag_handler=None, set_flag_handler=None,
                         connection_timeout=connection_timeout,
                         timeout=timeout, tcp_keepalive=tcp_keepalive, tcp_nodelay=tcp_nodelay,
                         exceptions=exceptions, base_backoff=base_backoff, max_retries=max_retries)
