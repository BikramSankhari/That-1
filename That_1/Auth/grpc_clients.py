import grpc
from .proto.AuthRediss import authRediss_pb2_grpc
from .proto.Auth import auth_pb2_grpc
import os

_sync_rediss_channel = None
_sync_rediss_stub = None

_async_rediss_channel = None
_async_rediss_stub = None

_peer_channel = None
_peer_stub = None
      
# Used in bloom_manager.py during startup
def get_sync_rediss_stub():
    global _sync_rediss_channel, _sync_rediss_stub
    if _sync_rediss_stub is None:
        _sync_rediss_channel = grpc.insecure_channel(
            f"{os.environ.get('REDISS_SERVICE_NAME')}:{os.environ.get('REDISS_SERVICE_PORT')}",
        )
        _sync_rediss_stub = authRediss_pb2_grpc.AuthRedissStub(_sync_rediss_channel)
    return _sync_rediss_stub

def close_sync_rediss_stub():
    global _sync_rediss_channel, _sync_rediss_stub
    if _sync_rediss_channel:
        _sync_rediss_channel.close()

    _sync_rediss_channel = None
    _sync_rediss_stub = None

# Used in bloom_manager.py during startup
def get_peer_stub():
    global _peer_channel, _peer_stub
    if _peer_stub is None:
        _peer_channel = grpc.insecure_channel(
            f"{os.environ.get('AUTH_BACKEND_SERVICE_NAME')}:{os.environ.get('AUTH_BACKEND_SERVICE_PORT')}",
        )
        _peer_stub = auth_pb2_grpc.AuthStub(_peer_channel)
    return _peer_stub

def close_peer_stub():
    global _peer_channel, _peer_stub
    if _peer_channel:
        _peer_channel.close()

    _peer_channel = None
    _peer_stub = None


def get_async_rediss_stub():
    global _async_rediss_channel, _async_rediss_stub
    if _async_rediss_stub is None:
        _async_rediss_channel = grpc.aio.insecure_channel(
            f"{os.environ.get('REDISS_SERVICE_NAME')}:{os.environ.get('REDISS_SERVICE_PORT')}",
        )
        _async_rediss_stub = authRediss_pb2_grpc.AuthRedissStub(_async_rediss_channel)
    return _async_rediss_stub

async def close_async_rediss_stub():
    global _async_rediss_channel, _async_rediss_stub
    if _async_rediss_channel:
        await _async_rediss_channel.close()
    _async_rediss_channel = None
    _async_rediss_stub = None