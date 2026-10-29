"""Reuse service-role HTTP connection pools within a worker thread.

Never pool user-authenticated clients: their sessions/headers are mutable.
"""
import os
import ssl
from threading import local

import certifi
import httpx
from supabase import ClientOptions, create_client

_local = local()
# TLS verification stays enabled. Reuse the immutable trust store rather than
# loading another certificate bundle for each worker's HTTP client.
_tls = ssl.create_default_context(cafile=os.getenv('SSL_CERT_FILE') or certifi.where())


def service_client_for(url, key):
    identity = (url, key)
    if getattr(_local, 'identity', None) != identity:
        previous = getattr(_local, 'transport', None)
        if previous:
            previous.close()
        transport = httpx.Client(
            verify=_tls, http2=False,
            headers={'apikey': key, 'Authorization': f'Bearer {key}'},
            timeout=httpx.Timeout(20, connect=5, pool=5),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        )
        _local.client = create_client(url, key, options=ClientOptions(
            httpx_client=transport, auto_refresh_token=False, persist_session=False,
        ))
        _local.transport = transport
        _local.identity = identity
    return _local.client


def read_with_retry(read):
    """One retry for network failures on reads only; never retry writes here."""
    try:
        return read()
    except httpx.TransportError:
        return read()
