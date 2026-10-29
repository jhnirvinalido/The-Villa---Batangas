"""Small Linux/Render memory snapshots; no request data or credentials."""
import asyncio
import logging
from pathlib import Path
import threading

logger = logging.getLogger("thevilla.memory")


def read_memory_snapshot(proc=Path("/proc/self/status"), cgroup=Path("/sys/fs/cgroup")):
    result = {"threads": threading.active_count()}
    try:
        fields = dict(line.split(":", 1) for line in proc.read_text().splitlines() if ":" in line)
        for source, target in (("VmRSS", "rss_mb"), ("VmHWM", "peak_rss_mb")):
            if source in fields:
                result[target] = round(int(fields[source].split()[0]) / 1024, 1)
    except (OSError, ValueError):
        pass
    # cgroup v2 reports the whole container, including file cache. It is
    # deliberately separate from process RSS rather than labelled as Python RAM.
    for source, target in (("memory.current", "container_mb"), ("memory.max", "limit_mb")):
        try:
            result[target] = round(int((cgroup / source).read_text().strip()) / 1048576, 1)
        except (OSError, ValueError):
            pass
    return result


async def monitor_memory(interval=30):
    while True:
        values = read_memory_snapshot()
        values["async_tasks"] = len(asyncio.all_tasks())
        report = logger.warning if values.get("container_mb", 0) > values.get("limit_mb", float("inf")) * 0.8 else logger.info
        report("Runtime memory: %s", " ".join(f"{key}={value}" for key, value in values.items()))
        await asyncio.sleep(interval)


def install_memory_monitor(app):
    task = None

    @app.on_event("startup")
    async def start():
        nonlocal task
        task = asyncio.create_task(monitor_memory())

    @app.on_event("shutdown")
    async def stop():
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
