'''
Customized over the aiomcache package to add connection_timeout functionality
'''

from .custom_pool import CustomPool
from .custom_client import CustomClient
import aiomcache
import sys

aiomcache.pool.MemcachePool = CustomPool
aiomcache.Client = CustomClient
sys.modules['aiomcache.client'].__dict__['MemcachePool'] = CustomPool

from aiomcache import *
