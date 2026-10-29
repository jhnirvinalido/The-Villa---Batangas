"""Reuse service-role HTTP connection pools within a worker thread.

Never pool user-authenticated clients: their sessions/headers are mutable.
"""
from threading import local
from supabase import create_client

_local = local()


def service_client_for(url, key):
    identity = (url, key)
    if getattr(_local, 'identity', None) != identity:
        _local.client = create_client(url, key)
        _local.identity = identity
    return _local.client
