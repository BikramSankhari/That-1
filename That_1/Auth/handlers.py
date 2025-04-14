from .services import UserService
from .proto import user_pb2_grpc

def grpc_handlers(server):
    user_pb2_grpc.add_UserControllerServicer_to_server(UserService.as_servicer(), server)