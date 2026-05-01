import asyncio
import os
import grpc.aio
from django.contrib.auth import get_user_model
from Auth.proto.Auth.auth_pb2 import IsValid, BloomResponseFromPeer
from django.db.utils import IntegrityError
from Auth.proto.Auth.auth_pb2_grpc import AuthServicer
from django.db import OperationalError, InterfaceError
from . import configurations
from That_1.utils import exponential_backoff_retry
from zstd import ZSTD_compress as compress
from datetime import datetime
from .utils import async_memcached
import asyncpg


User = get_user_model()

DB_ERRORS = (OperationalError, InterfaceError, asyncio.TimeoutError)


class AuthService(AuthServicer):
    def __init__(self, db_pool, bloom):
        super().__init__()
        self.pool = db_pool
        self.bloom = bloom

    async def UniqueValidate(self, request, context):
        email = request.email.strip().lower()

        # Bloom Filter Check
        if not self.bloom.exists(email):
            return IsValid(exists=False)

        # Check the Cache asynchronously
        email_active_status = await async_memcached.get(email, suppress=True)

        if email_active_status is not None:
            return IsValid(exists=True, is_active=email_active_status)

        # Fallback to DB
        @exponential_backoff_retry(base_backoff=configurations.BASE_DB_BACKOFF,
                                   max_retries=configurations.MAX_DB_RETRIES,
                                   exceptions=DB_ERRORS, is_async=True)
        async def get_user_status_from_db(email):
            async with self.pool.acquire() as connection:
                result = await connection.fetchrow(
                    "SELECT is_active FROM \"Auth_user\" WHERE email = $1", email)
                return result[0]

        try:
            email_active_status = await get_user_status_from_db(email)
        except DB_ERRORS as e:
            # Log the error here
            email_active_status = None

        if email_active_status is None:
            return IsValid(exists=False)

        # Update Cache if the email exists in DB
        await async_memcached.set(key=email, value=email_active_status, exptime=configurations.MEMCACHED_USER_ACTIVE_STATUS_TTL,
                                  retry=True, suppress=True)

        return IsValid(exists=True, is_active=email_active_status)

    async def GetBloomFromPeer(self, request, context):

        # Check the local memcached for a pre compressed bloom
        '''
        Here if the upcoming pod is on the same node then it will check the same memcached
        which the upcoming pod has already checked and failed. To avoid double checking memcached we
        need to pass the node name on which the upcoming pod has checked and then compare it 
        with the node name of this pod. But the time and cpu taken to serialize and deserialize the 
        node name , passing it over the network (as the request will come through a service) and then
        comparing against an environment variable will be even more than just a double check on same node
        '''
        compressed_bloom = None
        already_compressing = False

        compressed_bloom, already_compressing = await async_memcached.multi_get(
            [configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                configurations.BLOOM_COMPRESSION_LOCK_KEY],
            suppress=True)

        if compressed_bloom:
            return BloomResponseFromPeer(bloom=compressed_bloom)

        # If compressed bloom is not in cache then check if some other pod is already compressing the bloom
        if already_compressing:
            retries = 0
            while compressed_bloom is None and retries < configurations.MAX_MEMCACHED_ALREADY_COMPRESSING_RETRIES:
                await asyncio.sleep(configurations.BASE_MEMCACHED_ALREADY_COMPRESSING_BACKOFF)
                retries += 1
                try:
                    compressed_bloom = await async_memcached.get(
                        configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,)
                except Exception as e:
                    '''Can log the error here'''
                    break

            if compressed_bloom is not None:
                return BloomResponseFromPeer(bloom=compressed_bloom)

        # If no other pod is compressing then start compression
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        pod_id = os.environ.get("HOSTNAME", "unknown-pod")
        lock_value = f"{pod_id} :: {timestamp}"

        await async_memcached.set(
            key=configurations.BLOOM_COMPRESSION_LOCK_KEY, value=lock_value,
            exptime=configurations.BLOOM_COMPRESSION_LOCK_TTL,
            retry=True, suppress=True)

        try:
            # If in case the compresion fails then the lock will be released in finally block
            '''
            During compression the zstd algorithms takes some extra memory.
            So then it may run out of memory and raise MemoryError. This is just a case.
            '''
            compressed_bloom = compress(self.bloom.dump(), 1, 0)

        except MemoryError:
            '''Can log the error here'''
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED,
                          "Memory exhausted during Bloom filter compression")

        except Exception as e:
            '''Can log the error here'''
            context.abort(grpc.StatusCode.INTERNAL,
                          f"Internal error: {str(e)}")

        else:
            # Set the compressed bloom in cache for 1 minute
            await async_memcached.set(
                key=configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                value=compressed_bloom,
                exptime=configurations.COMPRESSED_BLOOM_TTL,
                retry=True, suppress=True)

            return BloomResponseFromPeer(bloom=compressed_bloom)

        finally:
            # Release the lock
            await async_memcached.delete(configurations.BLOOM_COMPRESSION_LOCK_KEY, retry=True, suppress=True)
