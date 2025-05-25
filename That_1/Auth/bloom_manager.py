import os, grpc, socket, bloompy
from struct import pack
from .proto import auth_pb2_grpc
from That_1.utils import exponential_backoff_retry
from bitarray import bitarray
from zstd import ZSTD_uncompress as uncompress
from google.protobuf import empty_pb2

bloom = None

retry_exceptions = (
    grpc.RpcError,
    TimeoutError,
    ConnectionError,
    socket.timeout,
    ConnectionResetError,
    OSError
)

class BloomFilter(bloompy.BloomFilter):
    def __init__(self,redis_host=os.environ.get('REDIS_HOST'), redis_port=os.environ.get('REDIS_PORT'), *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check for Redis first
        
        # Fallback to peer
        try:
            compressed_bloom = self.__get_bloom_from_peer()
            self.__load(compressed_bloom)
        except retry_exceptions:
            # Can log here
            pass

    def _at_half_fill(self):
        return self.bit_array.count()/len(self.bit_array)*1.0>=0.5
    
    def dump(self):
        return self.bit_array.tobytes()
    
    def __load(self, compressed_data):
        current_bloom = uncompress(compressed_data)
        self.bit_array.clear()
        self.bit_array.frombytes(current_bloom)

    @exponential_backoff_retry(base_backoff=0.5, max_retries=5, exceptions=retry_exceptions)
    def __get_bloom_from_peer(self):
        grpc_address = f"{os.environ.get('AUTH_BACKEND_SERVICE_NAME')}:{os.environ.get('AUTH_BACKEND_SERVICE_PORT')}"
        with grpc.insecure_channel(grpc_address) as channel:
            stub = auth_pb2_grpc.AuthStub(channel)
            response = stub.GetBloom(empty_pb2.Empty())

        return response.bloom