from That_1.That_1.custom_packages import AsyncMemcache
import asyncio
from That_1.That_1.custom_packages.AsyncMemcache.exceptions import ResponseTimeOut, ConnectionTimeout

client = AsyncMemcache.Client("127.0.0.1", 11211, connection_timeout=0.0000000001, timeout=0.1,
                              tcp_keepalive=True, tcp_nodelay=True, pool_size=3,
                              exceptions=(ResponseTimeOut, ConnectionTimeout),
                              base_backoff=0.5, max_retries=5)


async def retry_get(key):
    print(f"Getting key: {key}")
    value = await client.get(key=b'five')
    print(f"Get Value: {value}")


async def main():
    await asyncio.gather(retry_get(key=b"one"), retry_get(key=b"two"), retry_get(key=b"three"))

asyncio.run(main())
