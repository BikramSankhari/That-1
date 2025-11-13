import os
import grpc.aio
from .bloom_manager import bloomfilter
from django.contrib.auth import get_user_model
from proto.Auth.auth_pb2 import IsValid, BloomResponseFromPeer
from django.db.utils import IntegrityError
from proto.Auth.auth_pb2_grpc import AuthServicer
from django.db import OperationalError, InterfaceError
from . import configurations
from That_1.utils import exponential_backoff_retry
from bloom_manager import bloom
from zstd import ZSTD_compress as compress
from datetime import datetime
from .utils import memcached


User = get_user_model()

DB_ERRORS = (OperationalError, InterfaceError)

@exponential_backoff_retry(base_backoff=configurations.BASE_DB_BACKOFF,
                           max_retries=configurations.MAX_DB_RETRIES,
                           exceptions=DB_ERRORS)
def get_user_status_from_db(email):
    # The query returns None if the object is not found
    return User.objects.filter(email=email).values_list('is_active', flat=True).first()


class AuthService(AuthServicer):
    async def UniqueValidate(self, request, context):
        email = request.email.strip().lower()

        # Bloom Filter Check
        if not bloom.exists(email):
            return IsValid(exists=False)

        '''
        Here I can check in a local dict (or use cachetools library for eviction policy to keep the size maintained)
        It will be blazing fast like in nanoseconds, but will come at a cost of data duplication.
        Skipped to avoid memory bloat; reconsider if read load becomes a bottleneck depending on the specific business scenario.
        '''

        # Check the Cache asynchronously
        email_active_status = await memcached.async_get(email)

        if email_active_status is not None:
            return IsValid(exists=True, is_active=email_active_status)

        # Fallback to DB
        try:
            email_active_status = get_user_status_from_db(email)
        except DB_ERRORS as e:
            # Log the error here
            email_active_status = None

        if email_active_status is None:
            return IsValid(exists=False)

        # Update Cache if the email exists in DB
        memcached.retry_set(key=email, value=email_active_status)

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
        compressed_bloom = memcached.get(
            configurations.MEMCACHED_COMPRESSED_BLOOM_KEY)

        if compressed_bloom is not None:
            return BloomResponseFromPeer(bloom=compressed_bloom)

        bloom_compression_lock_key = "bloom_compression_lock"

        # If compressed bloom is not in cache then check if some other pod is already compressing the bloom
        already_compressing = memcached.get(bloom_compression_lock_key)

        if already_compressing:
            compressed_bloom = memcached.retry_get(configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                                                   base_backoff=configurations.BASE_MEMCACHED_ALREADY_COMPRESSING_BACKOFF,
                                                   max_retries=configurations.MAX_MEMCACHED_ALREADY_COMPRESSING_RETRIES)

            if compressed_bloom is not None:
                return BloomResponseFromPeer(bloom=compressed_bloom)

        # If no other pod is compressing then start compression
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        pod_id = os.environ.get("HOSTNAME", "unknown-pod")
        lock_value = f"{pod_id} :: {timestamp}"

        memcached.retry_set(key=bloom_compression_lock_key, value=lock_value)

        try:
            # If in case the compresion fails then the lock will be released
            '''
            During compression the zstd algorithms takes some extra memory.
            So then it may run out of memory and raise MemoryError. This is just a case.
            '''
            compressed_bloom = compress(bloom.dump(), 1, 0)

        except MemoryError:
            '''Can log the error here'''
            def abort(): return context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED,
                                              "Memory exhausted during Bloom filter compression")

        except Exception as e:
            '''Can log the error here'''
            def abort(): return context.abort(grpc.StatusCode.INTERNAL,
                                              f"Internal error: {str(e)}")

        else:
            # Set the compressed bloom in cache for 1 minute
            memcached.retry_set(
                key=configurations.MEMCACHED_COMPRESSED_BLOOM_KEY,
                value=compressed_bloom,
                timeout=configurations.COMPRESSED_BLOOM_TTL)

            abort = None

        finally:
            # Release the lock
            memcached.delete(bloom_compression_lock_key)
            if abort:
                abort()

        return BloomResponseFromPeer(bloom=compressed_bloom)
