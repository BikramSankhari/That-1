import os
import bloompy
from That_1.utils import exponential_backoff_retry
from zstd import ZSTD_uncompress as decompress
from google.protobuf import empty_pb2
from .utils import GRPC_EXCEPTIONS, DECOMPRESSION_EXCEPTIONS
from . import configurations
from .grpc_clients import get_sync_rediss_stub, close_sync_rediss_stub, get_peer_stub, close_peer_stub

# This variable is set during startup through the initialize_bloom() function in grpc server code
# and then imported by services.py
bloom = None


def initialize_bloom():
    global bloom
    bloom = BloomFilter(element_num=configurations.BLOOM_SIZE,
                        error_rate=configurations.BLOOM_ERROR_RATE)


class BloomFilter(bloompy.BloomFilter):
    def __init__(self, *args, **kwargs):    
        super().__init__(*args, **kwargs)

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
            return False
        else:
            if len(current_bloom) != len(self.bit_array.tobytes()):
                # Can log here
                return False

            self.bit_array.clear()
            self.bit_array.frombytes(current_bloom)
            return True

    def __load_bloom_from_rediss(self):

        @exponential_backoff_retry(base_backoff=configurations.BASE_REDISS_BACKOFF, max_retries=configurations.MAX_REDISS_RETRIES, exceptions=GRPC_EXCEPTIONS)
        def get_compressed_bloom_from_rediss():
            stub = get_sync_rediss_stub()
            response = stub.GetBloomFromRediss(empty_pb2.Empty())
            return response.bloom

        ''' Log that the bloom is being loaded from Rediss '''
        try:
            compressed_bloom = get_compressed_bloom_from_rediss()
        except GRPC_EXCEPTIONS:
            # Can log here
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            close_sync_rediss_stub()

    def __load_bloom_from_memcached(self):

        # Check local Memcached and if there is a network issue then retry
        @exponential_backoff_retry(base_backoff=configurations.BASE_MEMCACHED_BACKOFF, max_retries=configurations.MAX_MEMCACHED_RETRIES, exceptions=pylibmc.Timeout)
        def get_compressed_bloom_from_memcached(client: pylibmc.Client):
            return client.get(configurations.MEMCACHED_COMPRESSED_BLOOM_KEY)

        import pylibmc  # type: ignore
        client = pylibmc.Client([f"unix:{os.environ.get('MEMCACHED_UNIX_SOCKET')}"],
                                binary=True,
                                behaviors={"connect_timeout": int(configurations.MEMCACHED_CONNECTION_TIMEOUT * 1000),
                                           "send_timeout": configurations.ASYNC_MEMCACHED_SEND_TIMEOUT,
                                           "receive_timeout": configurations.ASYNC_MEMCACHED_RECV_TIMEOUT, }
                                )

        ''' Log that the bloom is being loaded from Memcached '''
        try:
            compressed_bloom = get_compressed_bloom_from_memcached(client)
        except Exception:
            # Log the error here
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            client.disconnect_all()


    def __load_bloom_from_peer(self):
        ''' Log that the bloom is being loaded from Peer '''
        @exponential_backoff_retry(base_backoff=configurations.BASE_PEER_BACKOFF, max_retries=configurations.MAX_PEER_RETRIES, exceptions=GRPC_EXCEPTIONS)
        def get_compressed_bloom_from_peer():
            stub = get_peer_stub()
            response = stub.GetBloomFromPeer(empty_pb2.Empty())
            return response.bloom

        try:
            compressed_bloom = get_compressed_bloom_from_peer()
        except GRPC_EXCEPTIONS:
            # Can log here
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            close_peer_stub()