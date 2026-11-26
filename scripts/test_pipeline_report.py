"""Check historical fidelity and HTML escaping without model calls."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import os
import time
from unittest.mock import patch, MagicMock
from urllib.parse import unquote

from build_pipeline_report import refresh, snapshot
import run_codex_pipeline as runner


class ReportTests(unittest.TestCase):
    def test_runner_publishes_success_and_failure_without_model_calls(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                run = Path(folder)/"demo"
                target = run/"default_camera_packet/default_camera_metadata.json"
                with patch("sys.argv", ["runner", "run", "--scene", "unused.blend", "--prompt", "test", "--to-stage", "1"]):
                    args = runner.parse_args()
                bridge = MagicMock()
                bridge.__enter__.return_value.environment.return_value = {}
                def execute(*a, **kw):
                    job = run/"codex/requests/fake-job"
                    job.mkdir(parents=True)
                    (job/"prompt.txt").write_text("fake offline request")
                    if fail:
                        raise subprocess.CalledProcessError(1, "fake")
                    target.parent.mkdir(parents=True)
                    target.write_text('{"ok": true}')
                    # Explicit nanoseconds avoid coarse filesystem write timestamps in this instant fake.
                    now = time.time_ns()
                    os.utime(target, ns=(now, now))
                with patch.object(runner, "get_staging_root", return_value=run), \
                     patch.object(runner, "validate_run_inputs"), \
                     patch.object(runner, "stage_commands", return_value=[("scene_packet", ["fake"], [target])]), \
                     patch.object(runner, "CodexBridge", return_value=bridge), \
                     patch.object(runner.subprocess, "run", side_effect=execute):
                    if fail:
                        with self.assertRaises(subprocess.CalledProcessError):
                            runner.run_pipeline(args)
                    else:
                        runner.run_pipeline(args)
                record = json.loads(next((run/"codex").glob("run-*.json")).read_text())
                self.assertEqual(record["status"], "failed" if fail else "succeeded")
                self.assertEqual(len(record["stages"][0]["jobs"]), 1)
                self.assertIn("outputs", record["stages"][0])
                self.assertTrue((run/"pipeline_report/index.html").is_file())

    def test_snapshot_survives_overwrite_and_binary_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)/"demo"
            (run/"asset_placement").mkdir(parents=True)
            original = run/"asset_placement/asset_placement_report.json"
            original.write_text('{"ok": true}')
            (run/"staged_scene.blend").write_bytes(b"binary-scene")
            entry = {"stage": 9}
            snapshot(run, run/"codex/run-1.json", entry, "outputs")
            saved = next(x for x in entry["outputs"] if x["source"] == str(original))
            binary = next(x for x in entry["outputs"] if x["source"].endswith(".blend"))
            original.write_text('{"ok": false}')
            self.assertEqual(Path(saved["snapshot"]).read_text(), '{"ok": true}')
            self.assertEqual(saved["sha256"], hashlib.sha256(b'{"ok": true}').hexdigest())
            self.assertNotIn("snapshot", binary)

    def test_legacy_failure_missing_output_escaping_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)/"demo with spaces"
            job = run/"codex/requests/job-one"
            job.mkdir(parents=True)
            job.joinpath("prompt.txt").write_text('<script>alert("oops")</script>')
            run.joinpath("codex/run-1.json").write_text(json.dumps({"status":"failed", "stages":[{
                "stage":2, "name":"scene_understanding", "status":"failed", "command":["no-model"],
                "error":"test failure", "jobs":[str(job)]}]}))
            output = refresh(run)
            content = output.read_text()
            self.assertNotIn('<script>alert("oops")</script>', content)
            self.assertIn('&lt;script&gt;', content)
            self.assertIn('旧记录未采集快照', content)
            self.assertIn('test failure', content)
            self.assertIn('缺失', content)
            class Links(HTMLParser):
                def handle_starttag(self, tag, attrs):
                    for key, value in attrs:
                        if key in ("href", "src") and not value.startswith("#"):
                            self_outer.assertTrue((output.parent/unquote(value)).is_file(), value)
            self_outer = self
            Links().feed(content)


if __name__ == "__main__":
    unittest.main()
