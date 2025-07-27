import os
import grpc
import socket
import bloompy
import redis.exceptions
import zstd
import redis
from .proto.Auth import auth_pb2_grpc
from .proto.AuthRediss import authRediss_pb2_grpc
from That_1.utils import exponential_backoff_retry
from zstd import ZSTD_uncompress as decompress
from google.protobuf import empty_pb2
from pympler.asizeof import asizeof
from .services import memcached
from . import configurations

bloom = None

ROOT_CERTIFICATE_PATH = os.environ["ROOT_CERTIFICATE_PATH"]

GRPC_EXCEPTIONS = (
    grpc.RpcError,
    TimeoutError,
    ConnectionError,
    socket.timeout,
    ConnectionResetError,
    OSError
)

DECOMPRESSION_EXCEPTIONS = (zstd.Error)


class BloomFilter(bloompy.BloomFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bloom_size_in_bytes = asizeof(self.bit_array)

        # Check for Rediss first
        if self.__load_bloom_from_rediss() is True:
            return
        
        # Check for Memcached
        elif self.__load_bloom_from_memcached() is True:
            return
        
        # Go for peer
        elif self.__load_bloom_from_peer() is True:
            return
        
        # Start with an empty bloom if all fails
        else:
            '''Can log that bloom is starting from scratch'''
            return

    def _at_half_fill(self):
        return self.bit_array.count()/len(self.bit_array)*1.0 >= 0.5

    def dump(self):
        return self.bit_array.tobytes()

    def __load(self, compressed_data):
        try:
            current_bloom = decompress(compressed_data)
        except DECOMPRESSION_EXCEPTIONS as e:
            # Can log here
            raise e
        else:
            self.bit_array.clear()
            self.bit_array.frombytes(current_bloom)
            return True

    def __load_bloom_from_rediss(self):

        @exponential_backoff_retry(base_backoff=configurations.BASE_REDISS_BACKOFF, max_retries=configurations.MAX_REDISS_RETRIES, exceptions=GRPC_EXCEPTIONS)
        def get_compressed_bloom_from_rediss():
            rediss_address = f"{os.environ.get('REDISS_ENDPOINT')}:{os.environ.get('REDISS_PORT')}"
            with grpc.insecure_channel(rediss_address) as channel:
                stub = authRediss_pb2_grpc.AuthRedissStub(channel)
                response = stub.GetBloomFromRediss(empty_pb2.Empty())

            return response.bloom
        
        ''' Log that the bloom is being loaded from Rediss '''

        try:
            compressed_bloom = get_compressed_bloom_from_rediss()
        except GRPC_EXCEPTIONS:
            # Can log here
            return False
        else:
            self.__load(compressed_bloom)
            return True


    def __load_bloom_from_memcached(self):
        # Check local Memcached and if there is a network issue then retry
        ''' Log that the bloom is being loaded from Memcached '''
        compressed_bloom = memcached.retry_get(
            configurations.MEMCACHED_COMPRESSED_BLOOM_KEY)

        if compressed_bloom is  None:
            return False
        
        else:
            try:
                self.__load(compressed_bloom)
                return True
            except DECOMPRESSION_EXCEPTIONS as e:
                # Can log here
                return False

    def __load_bloom_from_peer(self):
        ''' Log that the bloom is being loaded from Peer '''
        @exponential_backoff_retry(base_backoff=0.5, max_retries=5, exceptions=GRPC_EXCEPTIONS)
        def get_compressed_bloom_from_peer():
            # If the compression fails the peer pod will return None. In that case it will try again.
            grpc_address = f"{os.environ.get('AUTH_BACKEND_SERVICE_NAME')}:{os.environ.get('AUTH_BACKEND_SERVICE_PORT')}"
            with grpc.insecure_channel(grpc_address) as channel:
                stub = auth_pb2_grpc.AuthStub(channel)
                response = stub.GetBloom(empty_pb2.Empty())

            return response.bloom
        
        try:
            compressed_bloom = get_compressed_bloom_from_peer()
        except GRPC_EXCEPTIONS:
            # Can log here
            return False
        else:
            self.__load(compressed_bloom)
            return True
