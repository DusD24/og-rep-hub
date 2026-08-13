import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_SCRIPT = ROOT / "scripts" / "run_lock.sh"


class RunLockTests(unittest.TestCase):
    def _shell(self, script: str, *args: str, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", script, "run-lock-test", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

    def test_active_owner_returns_exit_75(self):
        with tempfile.TemporaryDirectory() as tempdir:
            lock_dir = str(Path(tempdir) / "active.lock")
            owner = subprocess.Popen(
                [
                    "bash",
                    "-c",
                    f"source {LOCK_SCRIPT}; acquire_run_lock \"$1\" owner; status=$?; [ $status -eq 0 ] || exit $status; sleep 2; release_run_lock \"$1\"",
                    "owner",
                    lock_dir,
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                for _ in range(20):
                    if Path(lock_dir).is_dir():
                        break
                    time.sleep(0.05)
                contender = self._shell(
                    f"source {LOCK_SCRIPT}; acquire_run_lock \"$1\" contender",
                    lock_dir,
                )
                self.assertEqual(contender.returncode, 75, contender.stderr)
            finally:
                owner.wait(timeout=5)

    def test_dead_owner_lock_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as tempdir:
            lock_dir = Path(tempdir) / "stale.lock"
            lock_dir.mkdir()
            (lock_dir / "pid").write_text("999999\n", encoding="utf-8")
            (lock_dir / "label").write_text("stale\n", encoding="utf-8")

            result = self._shell(
                f"source {LOCK_SCRIPT}; acquire_run_lock \"$1\" replacement; status=$?; [ $status -eq 0 ] || exit $status; test -f \"$1/pid\"; release_run_lock \"$1\"",
                str(lock_dir),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(lock_dir.exists())


if __name__ == "__main__":
    unittest.main()
