import tempfile
import unittest
from pathlib import Path

from runtime_memory import read_memory_snapshot


class RuntimeMemoryTests(unittest.TestCase):
    def test_process_and_container_memory_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / "status"
            proc.write_text("VmRSS:\t102400 kB\nVmHWM:\t204800 kB\n")
            (root / "memory.current").write_text(str(300 * 1048576))
            (root / "memory.max").write_text(str(512 * 1048576))
            result = read_memory_snapshot(proc, root)
            self.assertEqual(result["rss_mb"], 100)
            self.assertEqual(result["peak_rss_mb"], 200)
            self.assertEqual(result["container_mb"], 300)
            self.assertEqual(result["limit_mb"], 512)

    def test_missing_proc_or_unlimited_cgroup_does_not_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "memory.max").write_text("max")
            result = read_memory_snapshot(root / "missing", root)
            self.assertNotIn("limit_mb", result)
            self.assertNotIn("rss_mb", result)
            self.assertGreaterEqual(result["threads"], 1)
