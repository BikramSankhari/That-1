from That_1.custom_packages import AsyncMemcache
from That_1.custom_packages.AsyncMemcache.exceptions import ResponseTimeOut, ConnectionTimeout
from . import configurations
import os
import socket
import grpc
import zstandard
import logging

MEMCACHED_EXCEPTIONS = (ResponseTimeOut, ConnectionTimeout, socket.error)

DECOMPRESSION_EXCEPTIONS = (zstandard.ZstdError,)

GRPC_EXCEPTIONS = (
    grpc.RpcError,
    grpc.aio.AioRpcError,
    TimeoutError,
    ConnectionError,
    socket.timeout,
    ConnectionResetError,
    OSError
)

async_memcached = AsyncMemcache.Client(unix_socket=os.environ.get("MEMCACHED_UNIX_SOCKET"),
                                connection_timeout=configurations.MEMCACHED_CONNECTION_TIMEOUT, timeout=configurations.SYNC_MEMCACHED_TIMEOUT,
                                pool_size=configurations.MEMCACHED_POOL_SIZE,
                                exceptions=MEMCACHED_EXCEPTIONS,
                                base_backoff=configurations.BASE_MEMCACHED_BACKOFF,
                                max_retries=configurations.MAX_MEMCACHED_RETRIES)

logger = logging.getLogger("Auth")

POD_NAME = os.environ.get("POD_NAME")
NODE_NAME = os.environ.get("NODE_NAME")