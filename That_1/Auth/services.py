import asyncio
from multiprocessing import context
import os
import random
import grpc
from django.contrib.auth import get_user_model
from Auth.proto.Auth.auth_pb2 import IsValid, BloomResponseFromPeer
from django.db.utils import IntegrityError
from Auth.proto.Auth.auth_pb2_grpc import AuthServicer
from django.db import OperationalError, InterfaceError
from Auth import configurations
from That_1.utils import exponential_backoff_retry
import zstandard
from datetime import datetime
from Auth.utils import async_memcached, logger, MEMCACHED_EXCEPTIONS, POD_NAME, NODE_NAME
import asyncpg
from concurrent.futures import ThreadPoolExecutor
from That_1.Configurations import POD_NAME_METADATA_KEY, NODE_NAME_METADATA_KEY, REQUEST_ID_METADATA_KEY

User = get_user_model()

DB_ERRORS = (OperationalError, InterfaceError, asyncio.TimeoutError)


class AuthService(AuthServicer):
    def __init__(self, db_pool, bloom):
        super().__init__()
        self.pool = db_pool
        self.bloom = bloom
        self.executor = ThreadPoolExecutor(
            max_workers=configurations.MAX_THREAD_COUNT)
        self.semaphore = asyncio.Semaphore(configurations.SEMAPHORE_COUNT)
        self.memcached_compressor = zstandard.ZstdCompressor(level=1)

    async def UniqueValidate(self, request, context):
        metadata = dict(context.invocation_metadata())
        caller_pod = metadata.get(POD_NAME_METADATA_KEY, "unknown-pod")
        caller_node = metadata.get(NODE_NAME_METADATA_KEY, "unknown-node")
        request_id = metadata.get(
            REQUEST_ID_METADATA_KEY, "unknown-request-id")

        logger.info(
            f"Received UniqueValidate request for email: {request.email} from pod {caller_pod} on node {caller_node} with request id {request_id}")
        email = request.email.strip().lower()

        # Bloom Filter Check
        logger.info(f"Checking Bloom filter for email: {email}")
        if not self.bloom.exists(email):
            logger.info(
                f"Email: {email} does not exist in Bloom filter, returning response")
            
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME), (REQUEST_ID_METADATA_KEY, request_id)])
            return IsValid(exists=False)

        # Check the Cache asynchronously
        logger.info(f"Checking MemCache for email: {email} asynchronously")
        email_active_status = await async_memcached.get(email, suppress=True)

        if email_active_status is not None:
            logger.info(
                f"Email: {email} found in MemCache with active status: {email_active_status}, returning response")
                
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME), (REQUEST_ID_METADATA_KEY, request_id)])
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
            logger.info(f"Checking Database for email: {email} with asyncpg")
            email_active_status = await get_user_status_from_db(email)
        except DB_ERRORS as e:
            logger.warning(
                f"Database error while fetching status for email: {email}: {e}")
            email_active_status = None
        except Exception as e:
            logger.critical(
                f"Unexpected error while fetching user status from DB for email: {email} in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
            email_active_status = None

        if email_active_status is None:
            logger.info(
                f"Email: {email} does not exist in Database, returning response")
            
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME), (REQUEST_ID_METADATA_KEY, request_id)])
            return IsValid(exists=False)

        # Update Cache if the email exists in DB
        try:
            logger.info(
                f"Setting email: {email} with active status: {email_active_status} in MemCache asynchronously for next {configurations.MEMCACHED_USER_ACTIVE_STATUS_TTL} seconds")
            await async_memcached.set(key=email, value=email_active_status, exptime=configurations.MEMCACHED_USER_ACTIVE_STATUS_TTL,
                                      retry=True)
        except Exception as e:
            logger.warning(
                f"MemCache error while setting email: {email} with active status: {email_active_status}: {e}")

        logger.info(
            f"Email: {email} exists in Database with active status: {email_active_status}, returning response")
        
        await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME), (REQUEST_ID_METADATA_KEY, request_id)])
        return IsValid(exists=True, is_active=email_active_status)

    async def GetBloomFromPeer(self, request, context):

        metadata = dict(context.invocation_metadata())
        caller_pod = metadata.get(POD_NAME_METADATA_KEY, "unknown-pod")
        caller_node = metadata.get(NODE_NAME_METADATA_KEY, "unknown-node")

        logger.info(
            f"Received request for Bloom filter from pod: {caller_pod} on node: {caller_node}")

        # Check the local memcached for a pre compressed bloom
        compressed_bloom = None
        already_compressing = False

        logger.info("Checking local Memcached for compressed Bloom filter")

        memcached_result = await async_memcached.multi_get(
            [configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                configurations.BLOOM_COMPRESSION_LOCK_KEY],
            suppress=True)

        try:
            iter(memcached_result)
        except TypeError:
            compressed_bloom = None
            already_compressing = False
        else:
            compressed_bloom = memcached_result[0]
            already_compressing = memcached_result[1]

        if compressed_bloom:
            logger.info(
                "Compressed Bloom filter found in Memcached, sending response")
            
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])
            return BloomResponseFromPeer(bloom=compressed_bloom)

        # If compressed bloom is not in cache then check if some other pod is already compressing the bloom
        async def poll_memcached_for_compressed_bloom():
            compressed_bloom = None
            retries = 0
            while compressed_bloom is None and retries < configurations.MAX_MEMCACHED_ALREADY_COMPRESSING_RETRIES:
                logger.info(
                    f"Polling Memcached for compressed Bloom filter, attempt {retries}/{configurations.MAX_MEMCACHED_ALREADY_COMPRESSING_RETRIES}")
                retries += 1
                try:
                    compressed_bloom = await async_memcached.get(
                        configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,)

                except MEMCACHED_EXCEPTIONS as e:
                    logger.exception(
                        f"Error while polling Memcached for compressed Bloom filter: {e}")

                except Exception as e:
                    logger.critical(
                        f"Unexpected error while polling Memcached for compressed Bloom filter in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
                    logger.info(
                        "Breaking out of polling loop due to unexpected error")
                    break

                if compressed_bloom is None:
                    wait_time = configurations.BASE_MEMCACHED_ALREADY_COMPRESSING_BACKOFF * (1 + random.random())
                    logger.info(
                        f"Compressed Bloom filter not found in Memcached, waiting for {wait_time:.2f} seconds before next poll")

                    await asyncio.sleep(wait_time)
            return compressed_bloom

        if already_compressing:
            logger.info(
                "already_compressing flag is set in Memcached, polling for compressed Bloom filter")
            compressed_bloom = await poll_memcached_for_compressed_bloom()

        if compressed_bloom is not None:
            logger.info(
                "Compressed Bloom filter found in Memcached during polling, sending response")
            
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])
            return BloomResponseFromPeer(bloom=compressed_bloom)

        # If no other pod is compressing then start compression
        logger.info(
            "No compressed Bloom filter in Memcached and no other pod is compressing, starting compression")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        lock_value = f"{POD_NAME} :: {timestamp}"

        logger.info("Acquiring lock for Bloom filter compression")
        lock_acquired = await async_memcached.add(
            key=configurations.BLOOM_COMPRESSION_LOCK_KEY, value=lock_value,
            exptime=configurations.BLOOM_COMPRESSION_LOCK_TTL,
            retry=True, suppress=True)

        if not lock_acquired:
            # If lock is not acquired then it means some other pod has acquired the lock just now, so we can poll memcached for compressed bloom
            logger.info(
                "Failed to acquire lock, polling memcached for compressed Bloom filter")
            compressed_bloom = await poll_memcached_for_compressed_bloom()

        if compressed_bloom is not None:
            logger.info(
                "Compressed Bloom filter found in Memcached during polling after failed lock acquisition, sending response")
            
            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])
            return BloomResponseFromPeer(bloom=compressed_bloom)

        try:
            # If in case the compresion fails then the lock will be released in finally block
            '''
            During compression the zstd algorithms takes some extra memory.
            So then it may run out of memory and raise MemoryError. This is just a case.
            '''
            def compress_bloom():
                logger.info("Compressing Bloom filter")
                return self.memcached_compressor.compress(self.bloom.dump())

            loop = asyncio.get_running_loop()

            async with self.semaphore:
                logger.info(
                    "Offloading Bloom filter compression to thread pool executor")
                compressed_bloom = await loop.run_in_executor(self.executor, compress_bloom)

        except MemoryError:
            logger.critical(
                f"Memory exhausted during Bloom filter compression in pod {POD_NAME} on node {NODE_NAME}", exc_info=True)
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED,
                                "Memory exhausted during Bloom filter compression")

        except Exception as e:
            logger.critical(
                f"Unexpected error during Bloom filter compression in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL,
                                f"Internal error: {str(e)}")

        else:
            # Set the compressed bloom in cache for 1 minute
            logger.info(
                "Bloom filter compressed successfully, setting it in Memcached and sending response")

            try:
                await async_memcached.set(
                    key=configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                    value=compressed_bloom,
                    exptime=configurations.COMPRESSED_BLOOM_TTL,
                    retry=True)

            except Exception as e:
                logger.warning(
                    f"Failed to set compressed Bloom filter in Memcached due to error: {e}")
            else:
                logger.info(
                    "Compressed Bloom filter set in Memcached successfully")

            await context.send_initial_metadata([(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])
            return BloomResponseFromPeer(bloom=compressed_bloom)

        finally:
            # Release the lock
            logger.info("Releasing lock for Bloom filter compression")
            await async_memcached.delete(configurations.BLOOM_COMPRESSION_LOCK_KEY, retry=True, suppress=True)
