import asyncio
import asyncpg
import grpc
from .bloom_manager import initialize_bloom
import os
from . import configurations
from proto.Auth import auth_pb2_grpc
from .services import AuthService

async def serve():
    # Initialize the bloom filter before starting the server
    bloom = initialize_bloom()

    # Create the pool for PostgreSQL connections
    db_pool = await asyncpg.create_pool(user=os.environ.get('DB_USER'),
                                     password=os.environ.get('DB_PASSWORD'),
                                     database=os.environ.get('DB_NAME'),
                                     host=os.environ.get('DB_HOST'),
                                     port=os.environ.get('DB_PORT', '5432'),

                                     min_size=configurations.MINIMUM_POSTGRESQL_ASYNC_POOL_SIZE,
                                     max_size=configurations.MAXIMUM_POSTGRESQL_ASYNC_POOL_SIZE,
                                     max_inactive_connection_lifetime=300,
                                     timeout=5,
                                     command_timeout=5)

    server = grpc.aio.server()

    auth_pb2_grpc.add_AuthServicer_to_server(AuthService(db_pool, bloom), server)

    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    await server.start()
    print(f'Server started on {listen_addr}...')
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve())