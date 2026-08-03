import os
import bloompy
from That_1.utils import exponential_backoff_retry
import zstandard
from google.protobuf import empty_pb2
from Auth.utils import GRPC_EXCEPTIONS, DECOMPRESSION_EXCEPTIONS, logger, POD_NAME, NODE_NAME
from Auth import configurations
from Auth.grpc_clients import get_sync_rediss_stub, close_sync_rediss_stub, get_peer_stub, close_peer_stub
from That_1.Configurations import POD_NAME_METADATA_KEY, NODE_NAME_METADATA_KEY

# This functions initiates the bloom. It is called in server.py and the bloom is passes to the servicer
def initialize_bloom():
    bloom = BloomFilter(element_num=configurations.BLOOM_SIZE,
                        error_rate=configurations.BLOOM_ERROR_RATE)

    return bloom


class BloomFilter(bloompy.BloomFilter):
    def __init__(self, *args, **kwargs):    
        super().__init__(*args, **kwargs)
        self.decompressor = zstandard.ZstdDecompressor()

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
            logger.warning("Starting Bloom Filter from scratch")
            return

    def _at_half_fill(self):
        return self.bit_array.count()/len(self.bit_array)*1.0 >= 0.5

    def dump(self):
        return self.bit_array.tobytes()

    def __load(self, compressed_data):

        try:
            current_bloom = self.decompressor.decompress(compressed_data)
        except DECOMPRESSION_EXCEPTIONS as e:
            logger.exception(e)
            return False
        else:
            if len(current_bloom) != len(self.bit_array.tobytes()):
                logger.warning("Loaded Bloom Filter has incorrect size")
                return False

            self.bit_array.clear()
            self.bit_array.frombytes(current_bloom)

            logger.info("Bloom Filter loaded successfully with %d elements and %.6f error rate", self.element_num, self.error_rate)
            return True

    def __load_bloom_from_rediss(self):

        @exponential_backoff_retry(base_backoff=configurations.BASE_REDISS_BACKOFF, 
                                   max_retries=configurations.MAX_REDISS_RETRIES, 
                                   exceptions=GRPC_EXCEPTIONS,
                                   logger=logger,
                                   log_level="WARNING")
        def get_compressed_bloom_from_rediss():
            stub = get_sync_rediss_stub()
            response, call = stub.GetBloomFromRediss.with_call(empty_pb2.Empty(),
                                               metadata=[(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])
            
            server_initial_metadata = dict(call.initial_metadata())
            server_pod_name = server_initial_metadata.get(POD_NAME_METADATA_KEY, "Unknown")
            server_node_name = server_initial_metadata.get(NODE_NAME_METADATA_KEY, "Unknown")

            logger.info(f"Received response from Rediss pod : {server_pod_name} on node : {server_node_name}")
            return response.bloom

        logger.info("Initializing Bloom Filter from Rediss")

        try:
            compressed_bloom = get_compressed_bloom_from_rediss()
        except GRPC_EXCEPTIONS as e:
            logger.exception(e)
            return False
        except Exception as e:
            logger.critical(f"Unexpected error while connecting to Rediss in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            close_sync_rediss_stub()

    def __load_bloom_from_memcached(self):
        import pylibmc  # type: ignore

        pylibmc_exceptions = (pylibmc.ConnectionError, pylibmc.ServerDown)

        # Check local Memcached
        @exponential_backoff_retry(base_backoff=configurations.BASE_MEMCACHED_BACKOFF,
                                   max_retries=configurations.MAX_MEMCACHED_RETRIES, 
                                   exceptions=pylibmc_exceptions,
                                   logger=logger,
                                   log_level="WARNING")
        def get_compressed_bloom_from_memcached(client: pylibmc.Client):
            return client.get(configurations.MEMCACHED_COMPRESSED_BLOOM_KEY)

        logger.info("Initializing Bloom Filter from Memcached")

        client = pylibmc.Client([f"{os.environ.get('MEMCACHED_UNIX_SOCKET')}"],
                                binary=True,
                                behaviors={"connect_timeout": int(configurations.MEMCACHED_CONNECTION_TIMEOUT * 1000),
                                           "send_timeout": configurations.ASYNC_MEMCACHED_SEND_TIMEOUT,
                                           "receive_timeout": configurations.ASYNC_MEMCACHED_RECV_TIMEOUT, }
                                )

        try:
            compressed_bloom = get_compressed_bloom_from_memcached(client)
        except pylibmc_exceptions as e:
            logger.exception(e)
            return False
        except Exception as e:
            logger.critical(f"Unexpected error while connecting to Memcached in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            client.disconnect_all()


    def __load_bloom_from_peer(self):

        @exponential_backoff_retry(base_backoff=configurations.BASE_PEER_BACKOFF, 
                                   max_retries=configurations.MAX_PEER_RETRIES, 
                                   exceptions=GRPC_EXCEPTIONS,
                                   logger=logger,
                                   log_level="WARNING")
        def get_compressed_bloom_from_peer():
            stub = get_peer_stub()
            response, call = stub.GetBloomFromPeer.with_call(empty_pb2.Empty(),
                                             metadata=[(POD_NAME_METADATA_KEY, POD_NAME), (NODE_NAME_METADATA_KEY, NODE_NAME)])

            server_initial_metadata = dict(call.initial_metadata())
            server_pod_name = server_initial_metadata.get(POD_NAME_METADATA_KEY, "Unknown")
            server_node_name = server_initial_metadata.get(NODE_NAME_METADATA_KEY, "Unknown")

            logger.info(f"Received response from peer pod : {server_pod_name} on node : {server_node_name}")
            return response.bloom

        try:
            compressed_bloom = get_compressed_bloom_from_peer()
        except GRPC_EXCEPTIONS as e:
            logger.exception(e)
            return False
        except Exception as e:
            logger.critical(f"Unexpected error while connecting to peer for loading bloom in pod {POD_NAME} on node {NODE_NAME}: {e}", exc_info=True)
            return False
        else:
            return self.__load(compressed_bloom)
        finally:
            close_peer_stub()