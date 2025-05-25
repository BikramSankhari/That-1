import socket
from bloom_manager import bloomfilter
from django.contrib.auth import get_user_model
from proto.auth_pb2 import IsValid, BloomResponse
from django.db.utils import IntegrityError
from proto.auth_pb2_grpc import AuthServicer
from django.core.cache import cache
from django.db import OperationalError, InterfaceError
from .configurations import MAX_DB_RETRIES, BASE_DB_BACKOFF, BLOOM_SIZE
from That_1.utils import exponential_backoff_retry
from bloom_manager import bloom
from zstd import ZSTD_compress as compress
import pylibmc # type: ignore

User = get_user_model()
bloom = bloomfilter(error_rate=0.001,element_num=BLOOM_SIZE)

@exponential_backoff_retry(base_backoff=BASE_DB_BACKOFF, max_retries=MAX_DB_RETRIES, 
                           exceptions=(OperationalError,InterfaceError))
def get_user_status_from_db(email):
    # The query returns None if the object is not found
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
        Skipped to avoid memory bloat; reconsider if read load becomes a bottleneck depending on the specific business scenario.
        '''

        # Check the Cache
        email_active_status = cache_set_or_get(key=email, action='get')
       
        if email_active_status is not None:
            return IsValid(exists=True, is_active=email_active_status)
        
        # Fallback to DB
        try:
            email_active_status = get_user_status_from_db(email)
        except (OperationalError, InterfaceError) as e:
            # Log the error here
            email_active_status = None

        if email_active_status is None:
            return IsValid(exists=False)

        # Update Cache if the email exists in DB
        cache_set_or_get(key=email, value=email_active_status, action='set')

        return IsValid(exists=True, is_active=email_active_status)
    
    def GetBloom(self, request, context):
        compressed_bloom = compress(bloom.dump(), 1, 0)
        return BloomResponse(bloom=compressed_bloom)