import socket
from aiomcache.pool import MemcachePool, Connection
import asyncio
from typing import Optional
from .exceptions import ConnectionTimeout


class CustomPool(MemcachePool):
    def __init__(self, host, port, unix_socket=None, *, minsize, maxsize, conn_args=None, connection_timeout: float,
                 tcp_keepalive: bool, tcp_nodelay: bool):

        super().__init__(host, port, minsize=minsize, maxsize=maxsize, conn_args=conn_args)

        self.connection_timeout = connection_timeout
        self.tcp_keep_alive = tcp_keepalive
        self.tcp_nodelay = tcp_nodelay
        self.unix_socket = unix_socket

    """
    Creates a new Memcache connection with timeout and socket options.
    Raises ConnectionTimeout if the connection cannot be established within connection_timeout.
    """
    async def _create_new_conn(self) -> Optional[Connection]:

        if self.size() >= self._maxsize:
            return None
        
        loop = asyncio.get_running_loop()

        if self.unix_socket:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self.unix_socket),
                    timeout=self.connection_timeout
                )
            except TimeoutError:
                raise ConnectionTimeout("Connection Timed Out")
        
        else:
            custom_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            custom_socket.setblocking(False)

            if self.tcp_keep_alive:
                custom_socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            if self.tcp_nodelay:
                custom_socket.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
            try:
                await asyncio.wait_for(
                    loop.sock_connect(custom_socket, (self._host, self._port)),
                    timeout=self.connection_timeout
                )

            except TimeoutError:
                custom_socket.close()
                raise ConnectionTimeout("Connection Timed Out")
            
            else:
                try:
                    reader, writer = await asyncio.open_connection(sock=custom_socket, **self.conn_args)

                except Exception as e:
                    custom_socket.close()
                    raise e

        # Here we need to check self.size() again because while awaiting a coroutine, the event loop may acquire other connection and the size may reach max_size
        if self.size() < self._maxsize:
            return Connection(reader, writer)
        else:
            reader.feed_eof()
            writer.close()
            await writer.wait_closed()
            return None

