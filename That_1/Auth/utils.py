from That_1.utils import DjangoCacheInteractor
from That_1.Configurations import MEMCACHED_ALIAS
import pylibmc  # type: ignore
import socket
from . import configurations


MEMCACHED_EXCEPTIONS = (pylibmc.Error, socket.timeout, socket.error)


memcached = DjangoCacheInteractor(alias_name=MEMCACHED_ALIAS, exceptions=MEMCACHED_EXCEPTIONS,
                            base_backoff=configurations.BASE_MEMCACHED_BACKOFF,
                            max_retries=configurations.MAX_MEMCACHED_RETRIES)
