import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / name
    if not path.exists():
        raise AssertionError(f"Missing release script: {path}")
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SiteConfigBuildTests(unittest.TestCase):
    def run_builder(self, endpoint, site_key):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site_config.json"
        environment = os.environ.copy()
        environment.update({"ISSUE_INTAKE_URL": endpoint, "TURNSTILE_SITE_KEY": site_key})
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_site_config.py"), "--output", str(output)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        return result, output

    def test_builder_emits_public_runtime_configuration(self):
        result, output = self.run_builder("https://og-rep-hub-issue-intake.example.workers.dev/", "0x4-public-site-key")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {
            "issue_intake_url": "https://og-rep-hub-issue-intake.example.workers.dev",
            "turnstile_site_key": "0x4-public-site-key",
        })

    def test_builder_rejects_missing_or_non_https_configuration(self):
        for endpoint, site_key in (("http://worker.example", "site-key"), ("https://worker.example", "")):
            with self.subTest(endpoint=endpoint, site_key=site_key):
                result, output = self.run_builder(endpoint, site_key)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())


class ReleaseMetaBuildTests(unittest.TestCase):
    def run_builder(self, sha):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "build-meta.json"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_release_meta.py"),
                "--output",
                str(output),
                "--sha",
                sha,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        return result, output

    def test_builder_emits_exact_commit_sha(self):
        sha = "a" * 40
        result, output = self.run_builder(sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"commit_sha": sha})

    def test_builder_rejects_non_commit_values(self):
        result, output = self.run_builder("main")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


class LiveReleaseVerificationTests(unittest.TestCase):
    def test_poll_requires_pages_and_worker_to_report_the_same_sha(self):
        verifier = load_script("verify_release.py")
        sha = "b" * 40
        calls = []

        def fetch_json(url):
            calls.append(url)
            if url.endswith("build-meta.json"):
                return {"commit_sha": sha}
            return {"ok": True, "buildSha": sha}

        self.assertTrue(verifier.poll_for_sha(
            "https://dusd24.github.io/og-rep-hub/",
            "https://worker.example/",
            sha,
            attempts=1,
            interval=0,
            fetch_json=fetch_json,
            sleep=lambda _seconds: None,
        ))
        self.assertEqual(calls, [
            "https://dusd24.github.io/og-rep-hub/build-meta.json",
            "https://worker.example/health",
        ])

    def test_poll_retries_until_both_sha_markers_match(self):
        verifier = load_script("verify_release.py")
        sha = "c" * 40
        worker_calls = 0

        def fetch_json(url):
            nonlocal worker_calls
            if url.endswith("build-meta.json"):
                return {"commit_sha": sha}
            worker_calls += 1
            return {"ok": True, "buildSha": "old" if worker_calls == 1 else sha}

        self.assertTrue(verifier.poll_for_sha(
            "https://pages.example/project",
            "https://worker.example",
            sha,
            attempts=2,
            interval=0,
            fetch_json=fetch_json,
            sleep=lambda _seconds: None,
        ))
        self.assertEqual(worker_calls, 2)


class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_pull_requests_validate_worker_and_main_deploys_worker_before_pages(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("pnpm test", workflow)
        self.assertIn("wrangler deploy", workflow)
        self.assertIn("deploy-worker:", workflow)
        self.assertRegex(workflow, r"deploy:\n(?:.*\n)*?\s+needs: \[validate, deploy-worker\]")
        self.assertLess(workflow.index("deploy-worker:"), workflow.index("\n  deploy:"))
        self.assertIn("scripts/build_site_config.py", workflow)
        self.assertIn("scripts/build_release_meta.py", workflow)
        self.assertIn("scripts/verify_release.py", workflow)


if __name__ == "__main__":
    unittest.main()
