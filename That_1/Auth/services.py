import socket
import bloompy
from django.contrib.auth import get_user_model
from proto.auth_pb2 import IsValid
from django.db.utils import IntegrityError
from proto.auth_pb2_grpc import AuthServicer
from django.core.cache import cache
from django.db import OperationalError, InterfaceError
from configurations import MAX_DB_RETRIES, BASE_DB_BACKOFF
from That_1.utils import exponential_backoff_retry
import pylibmc # type: ignore

User = get_user_model()
bloom = bloompy.BloomFilter(error_rate=0.001,element_num=1000)

@exponential_backoff_retry(base_backoff=BASE_DB_BACKOFF, max_retries=MAX_DB_RETRIES, 
                           exceptions=(OperationalError,InterfaceError))
def get_user(email):
    return User.objects.filter(email=email).values_list('is_active', flat=True).first()

def cache_set_or_get(key=None, value=None, action='get'):
    try:
        if action == 'set':
            cache.set(key, value)
        elif action == 'get':
            return cache.get(key)
        else:
            raise ValueError("Invalid action. Use 'get' or 'set'.")
        
    except (pylibmc.Error, socket.error, socket.timeout) as e:
        ''' Can Log the error here '''
        return None

class AuthService(AuthServicer):
    def UniqueValidate(self, request, context):
        email = request.email.strip().lower()

        # Bloom Filter Check
        if not bloom.exists(email):
            return IsValid(exists=False)
        
        '''
        Here I can check in a local dict (or use cachetools library for eviction policy to keep the size maintained)
        It will be blazing fast like in nanoseconds, but will come at a cost of data duplication.
        So for now not using it. It will depend on the specific business scenario.
        '''

        # Check the Cache
        email_is_active = cache_set_or_get(key=email, action='get')
       
        if email_is_active is not None:
            return IsValid(exists=True, is_active=email_is_active)
        
        # Fallback to DB
        try:
            result = get_user(email)
        except (OperationalError, InterfaceError) as e:
            # Log the error here
            result = None

        if result is None:
            return IsValid(exists=False)

        # Update Cache if the email exists in DB
        cache_set_or_get(key=email, value=result, action='set')

        return IsValid(exists=True, is_active=result)