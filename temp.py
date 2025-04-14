import grpc
from That_1.Auth.proto import user_pb2, user_pb2_grpc


with grpc.insecure_channel('localhost:50051') as channel:
    stub = user_pb2_grpc.UserControllerStub(channel)
    print('----- Create -----')
    response = stub.Create(user_pb2.UserWithPassword(email="bikram1209@gmail.com", password="pass"))
    print(response, end='')