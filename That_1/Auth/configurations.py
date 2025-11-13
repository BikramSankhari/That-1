# (services.py)
MAX_DB_RETRIES = 3
BASE_DB_BACKOFF = 0.5

# (apps.py)
BLOOM_SIZE = 1000
BLOOM_ERROR_RATE = 0.001


BASE_MEMCACHED_BACKOFF = 0.2
MAX_MEMCACHED_RETRIES = 5
MEMCACHED_COMPRESSED_BLOOM_KEY = "compressed_bloom"
BASE_MEMCACHED_ALREADY_COMPRESSING_BACKOFF = 0.5
MAX_MEMCACHED_ALREADY_COMPRESSING_RETRIES = 5
COMPRESSED_BLOOM_TTL = 60
# Backoff for retrying Rediss to fetch the bloom filter. (bloom_manager.py)
BASE_REDISS_BACKOFF = 0.5

# Max retries for Rediss to fetch the bloom filter. (bloom_manager.py)
MAX_REDISS_RETRIES = 5