import grpc
from google.protobuf import empty_pb2
from django_grpc_framework.services import Service
from django.contrib.auth import get_user_model
from .serializers import UserProtoSerializer, UserWithPasswordProtoSerializer


class UserService(Service): 
    def List(self, request, context):
        users = get_user_model().objects.all()
        serializer = UserProtoSerializer(users, many=True, context=context)
        for msg in serializer.message:
            yield msg
    
    def Create(self, request, context):
        user = UserWithPasswordProtoSerializer(message=request, context=context)
        user.is_valid(raise_exception=True)
        user.save()
        return user.message
    
    def Retrieve(self, id, context):
        try:
            return get_user_model().objects.get(pk=id)
        except self.get_user().DoesNotExist:
            self.context.abort(grpc.StatusCode.NOT_FOUND, 'User not found')
    
    def Update(self, request, context):
        user = self.Retrieve(request.id, context)
        serializer = UserProtoSerializer(user, message=request, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return serializer.message
    
    def Destroy(self, request, context):
        user = self.Retrieve(request.id, context)
        user.delete()
        return empty_pb2.Empty()