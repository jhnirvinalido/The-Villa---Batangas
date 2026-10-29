"""Bounded concurrent independent reads; no shared response/auth cache."""
from concurrent.futures import ThreadPoolExecutor

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='villa-read')


def parallel_reads(reads):
    pending = {name: _pool.submit(read) for name, read in reads.items()}
    return {name: future.result() for name, future in pending.items()}
