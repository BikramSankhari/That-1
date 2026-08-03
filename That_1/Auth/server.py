import asyncio
import asyncpg
import grpc
import os
import django
from Auth.utils import logger

# Set django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'That_1.settings')
django.setup()


async def serve():
    from Auth.bloom_manager import initialize_bloom
    from Auth import configurations
    from Auth.proto.Auth import auth_pb2_grpc
    from Auth.services import AuthService
    from Auth.utils import POD_NAME, NODE_NAME

    # Log the startup of the server with pod and node information
    logger.info(f"Starting Auth Backend Server on pod {POD_NAME} on node {NODE_NAME}...")

    # Initialize the bloom filter before starting the server
    logger.info("Initializing Bloom Filter")
    bloom = initialize_bloom()

    # Create the pool for PostgreSQL connections
    logger.info("Creating PostgreSQL connection pool")
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
    logger.info(f'Server started on pod {POD_NAME} on node {NODE_NAME}...')
    logger.info("==============================================================================================")
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve())