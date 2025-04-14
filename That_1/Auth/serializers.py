from django_grpc_framework import proto_serializers
from django.contrib.auth import get_user_model
from .proto import user_pb2

class UserProtoSerializer(proto_serializers.ModelProtoSerializer):
    class Meta:
        model = get_user_model()
        proto_class = user_pb2.User
        fields = ['email',]

class UserWithPasswordProtoSerializer(proto_serializers.ModelProtoSerializer):
    class Meta:
        model = get_user_model()
        proto_class = user_pb2.UserWithPassword
        fields = ['email', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = self.Meta.model(**validated_data)
        if password:
            user.set_password(password)
        else:
            raise ValueError("Password is required")
        user.save()
        return user