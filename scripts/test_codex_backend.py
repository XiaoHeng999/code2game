"""Offline contract tests; no model calls, network downloads or GPU required."""
import base64
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from codex_backend import CodexBackend, CodexBridge, read_object
import run_codex_pipeline as runner


class BackendTests(unittest.TestCase):
    def test_json_object_required(self):
        self.assertEqual(read_object('```json\n{"ok": true}\n```'), {"ok": True})
        with self.assertRaises(ValueError):
            read_object("[]")

    def test_visual_payload_retains_image_and_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = CodexBackend(folder)
            with patch.object(backend, "invoke", return_value={"scene": "forest"}) as call:
                result = backend.chat({"model": "legacy-model", "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Describe this scene"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b"image-data").decode()}},
                ]}]})
            prompt, _, images = call.call_args.args
            self.assertIn("Describe this scene", prompt)
            self.assertEqual(images[0].read_bytes(), b"image-data")
            self.assertEqual(json.loads(result["choices"][0]["message"]["content"]), {"scene": "forest"})

    def test_remote_image_not_fetched(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                CodexBackend(folder).chat({"messages": [{"content": [
                    {"type": "image_url", "image_url": {"url": "http://localhost/private"}}]}]})

    def test_bridge_auth_and_legacy_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = CodexBackend(folder)
            with patch.object(backend, "chat", return_value={"choices": []}) as call, CodexBridge(backend) as bridge:
                env = bridge.environment({"CODE2GAMES_RULE_BASE_URL": "https://old.example"})
                self.assertEqual(env["CODE2GAMES_RULE_BASE_URL"], env["DASHSCOPE_BASE_URL"])
                url = env["OPENAI_BASE_URL"] + "/chat/completions"
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url, data=b"{}"))
                self.assertEqual(error.exception.code, 401)
                call.assert_not_called()
                request = urllib.request.Request(url, data=b"{}", headers={"Authorization": "Bearer " + bridge.token})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response), {"choices": []})

    def test_image_cannot_escape_job(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = CodexBackend(folder)
            with patch.object(backend, "invoke", return_value={"image_path": "/outside/reference.png", "error": ""}):
                with self.assertRaises(ValueError):
                    backend.generate_image("a chest", Path(folder) / "final.png")

    def test_mesh_worker_requires_reference_before_loading_hunyuan(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = Path(folder) / "plan.json"
            plan.write_text(json.dumps({"assets": [{"asset_id": "missing-test-reference", "asset_name": "chest",
                "generation_prompt_en": "chest", "expected_glb_path": "unused.glb"}]}))
            with patch("sys.argv", ["runner", "meshes", "--asset-plan", str(plan)]):
                args = runner.parse_args()
            with self.assertRaises(FileNotFoundError):
                runner.generate_meshes(args)

    def test_local_mesh_uses_dedicated_python(self):
        with patch("sys.argv", ["runner", "run", "--dry-run"]):
            args = runner.parse_args()
        stages = runner.stage_commands(args)
        self.assertEqual(len(stages), 12)
        self.assertEqual(stages[7][1][0], args.hunyuan_python)
        self.assertIn("--python-exit-code", stages[0][1])

    def test_timeout_stops_child_process_group(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = CodexBackend(folder, timeout=1)
            with patch("codex_backend.subprocess.Popen") as start, patch("codex_backend.os.killpg") as kill:
                child = start.return_value
                child.pid = 12345
                child.communicate.side_effect = subprocess.TimeoutExpired("codex", 1)
                with self.assertRaises(subprocess.TimeoutExpired):
                    backend.invoke("test", Path(folder) / "job")
                kill.assert_called_once()
                child.wait.assert_called_once_with(timeout=5)

    def test_image_existing_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "existing.png"
            destination.write_bytes(b"user-owned-image")
            with self.assertRaises(FileExistsError):
                CodexBackend(folder).generate_image("a chest", destination)
            self.assertEqual(destination.read_bytes(), b"user-owned-image")

    def test_scene_stages_do_not_require_fbx(self):
        with tempfile.TemporaryDirectory() as folder:
            scene = Path(folder) / "test.blend"
            scene.write_bytes(b"test-input")
            with patch("sys.argv", ["runner", "run", "--scene", str(scene), "--prompt", "test", "--to-stage", "9"]):
                args = runner.parse_args()
            runner.validate_run_inputs(args)
            args.to_stage = 12
            with self.assertRaisesRegex(ValueError, "Stage 10"):
                runner.validate_run_inputs(args)

    def test_rule_catalog_matches_validator_without_mutating_request(self):
        text = "Allowed element_type values: collectible, obstacle, event_trigger, goal_area, hazard_zone, safe_zone, landmark."
        payload = {"messages": [{"role": "user", "content": text}]}
        fixed = runner.normalize_rule_catalog(payload)
        self.assertIn("player_spawn", fixed["messages"][0]["content"])
        self.assertIn("objective_object", fixed["messages"][0]["content"])
        self.assertEqual(payload["messages"][0]["content"], text)

    def test_style_reference_is_attached_to_codex(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = Path(folder) / "scene.png"
            reference.write_bytes(b"reference-fixture")
            backend = CodexBackend(folder)
            with patch.object(backend, "invoke", return_value={"image_path": "", "error": "test-stop"}) as call:
                with self.assertRaisesRegex(RuntimeError, "test-stop"):
                    backend.generate_image("chest", Path(folder) / "result.png", [reference])
                self.assertEqual(call.call_args.kwargs["images"], [reference.resolve()])
                self.assertIn("actually include these images", call.call_args.args[0])

    def test_scene_profile_and_style_reference_reach_workers(self):
        with patch("sys.argv", ["runner", "run", "--dry-run", "--scene-profile", "profile.json", "--style-reference", "scene.png"]):
            args = runner.parse_args()
        stages = runner.stage_commands(args)
        self.assertTrue(stages[4][1][1].endswith("placement_context_adapter.py"))
        self.assertIn("--style-reference", stages[6][1])


if __name__ == "__main__":
    unittest.main()
