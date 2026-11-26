#!/usr/bin/env python3
"""Additive Codex + native image generation + Hunyuan pipeline entry point."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from unittest.mock import patch

from codex_backend import CodexBackend, CodexBridge
from build_pipeline_report import refresh as refresh_html_report, snapshot as snapshot_stage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared_representation"))
from staging_paths import get_staging_root, get_demo_name
from placement_constraints import ALLOWED_ELEMENT_TYPES


def normalize_rule_catalog(payload):
    """Correct the legacy prompt's stale seven-type list using its actual validator."""
    old = "Allowed element_type values: collectible, obstacle, event_trigger, goal_area, hazard_zone, safe_zone, landmark."
    new = "Allowed element_type values: " + ", ".join(sorted(ALLOWED_ELEMENT_TYPES)) + "."
    result = copy.deepcopy(payload)
    for message in result.get("messages", []):
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = content.replace(old, new)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    part["text"] = part["text"].replace(old, new)
    return result


class PipelineCodexBackend(CodexBackend):
    def chat(self, payload):
        return super().chat(normalize_rule_catalog(payload))


def asset_module():
    path = ROOT / "game_realization/asset_instantiation/run_asset_generation_stage.py"
    spec = importlib.util.spec_from_file_location("legacy_asset_generation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def require_files(paths):
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing required output/input: {path}")


def backend(args, suffix="requests", image=False):
    return PipelineCodexBackend(Path(get_staging_root(ROOT)) / "codex" / suffix,
                        args.codex, args.codex_model, args.image_timeout if image else args.codex_timeout)


def reference_paths(module, assets):
    result = []
    for asset in assets:
        name = module.sanitize_filename(asset["asset_id"]) + "_" + module.sanitize_filename(asset["asset_name"])
        result.append(module.REFERENCE_IMAGE_DIR / (name + ".png"))
    if len(set(result)) != len(result):
        raise ValueError("Reference image names collide after filename normalization")
    return result


def generate_images(args):
    from PIL import Image
    module = asset_module()
    assets = module.load_assets(module.load_json(args.asset_plan or module.DEFAULT_ASSET_PLAN))
    images = reference_paths(module, assets)
    manifest_path = module.OUTPUT_DIR / "codex_image_manifest.json"
    manifest = {"provider": "codex_native_image", "model": "tool-managed-unverified", "assets": []}
    write_json(manifest_path, manifest)
    generator = backend(args, "images", image=True)
    for asset, image in zip(assets, images):
        if args.reuse_images and image.is_file():
            with Image.open(image) as loaded:
                loaded.verify()
            entry = {"asset_id": asset["asset_id"], "status": "reused_unverified_provenance", "path": str(image)}
        else:
            print(f"Generating reference image: {asset['asset_id']}", flush=True)
            entry = {"asset_id": asset["asset_id"], "status": "running"}
            manifest["assets"].append(entry)
            write_json(manifest_path, manifest)
            try:
                entry.update(generator.generate_image(module.build_reference_prompt(asset), image, args.style_reference))
                entry["status"] = "succeeded"
            except Exception as exc:
                entry.update(status="failed", error=str(exc))
                write_json(manifest_path, manifest)
                raise
            write_json(manifest_path, manifest)
            continue
        manifest["assets"].append(entry)
        write_json(manifest_path, manifest)


def generate_meshes(args):
    """Reuse existing Hunyuan implementation, with no image-provider fallback."""
    from PIL import Image
    module = asset_module()
    plan_path = Path(args.asset_plan or module.DEFAULT_ASSET_PLAN)
    assets = module.load_assets(module.load_json(plan_path))
    for image in reference_paths(module, assets):
        require_files([image])
        with Image.open(image) as loaded:
            loaded.verify()
        if not module.is_valid_reference_image(image):
            raise ValueError(f"Reference image fails legacy preflight: {image}")

    def no_image_fallback(*_args, **_kwargs):
        raise RuntimeError("Reference image missing or invalid; run the images stage. DashScope fallback is disabled.")

    # Process-local compatibility adapter; no original source file is edited.
    module.generate_reference_image = no_image_fallback
    module.DASHSCOPE_IMAGE_MODEL = "codex-native-image/tool-managed-unverified"
    original_manifest = module.new_manifest

    def manifest_with_provenance(parsed_args):
        manifest = original_manifest(parsed_args)
        manifest["t2i_backend"] = "existing_reference_images"
        manifest["t2i_model"] = "see codex_image_manifest.json or source image metadata"
        manifest.pop("t2i_size", None)
        manifest["image_fallback_disabled"] = True
        return manifest

    module.new_manifest = manifest_with_provenance
    argv = [str(module.__file__), "--asset_plan", str(plan_path), "--reuse_reference_images",
            "--hunyuan_backend", args.hunyuan_backend, "--server", args.hunyuan_server,
            "--hunyuan_repo", args.hunyuan_repo, "--model_path", args.weights,
            "--texgen_model_path", args.weights, "--export_texture"]
    if args.skip_existing:
        argv.append("--skip_existing")
    previous = sys.argv
    try:
        sys.argv = argv
        context = nullcontext()
        if args.hunyuan_backend == "local":
            # The upstream Gradio entry point applies this fix, but its imported
            # Paint pipeline does not. Match the official entry-point initialization.
            fix_path = Path(args.hunyuan_repo) / "hy3dpaint/utils/torchvision_fix.py"
            if fix_path.is_file():
                fix_spec = importlib.util.spec_from_file_location("hunyuan_torchvision_fix", fix_path)
                fix = importlib.util.module_from_spec(fix_spec)
                fix_spec.loader.exec_module(fix)
                if not fix.apply_fix():
                    raise RuntimeError("Hunyuan torchvision compatibility initialization failed")
        if args.hunyuan_backend == "local" and Path(args.weights).is_dir():
            import huggingface_hub
            original_snapshot = huggingface_hub.snapshot_download

            def local_snapshot(repo_id, *positional, **kwargs):
                # Upstream Paint treats this setting as a Hub ID even for a local path.
                # Redirect only this exact weight root; keep auxiliary downloads untouched.
                if repo_id == args.weights:
                    return str(Path(args.weights).resolve())
                return original_snapshot(repo_id, *positional, **kwargs)

            context = patch.object(huggingface_hub, "snapshot_download", local_snapshot)
        with context:
            module.main()
    finally:
        sys.argv = previous
    require_files([module.resolve_project_path(asset["expected_glb_path"]) for asset in assets])


def stage_commands(args):
    staging = Path(get_staging_root(ROOT))
    packet = staging / "default_camera_packet"
    plan = staging / "asset_realization/asset_plan.json"
    staged = staging / "staged_scene.blend"
    path = staging / "gameplay_path/gameplay_path.json"
    output = staging / "gameplay_output"
    scene = str(Path(args.scene).resolve()) if args.scene else "<scene.blend>"
    npc = str(Path(args.npc).resolve()) if args.npc else "<animated-npc.fbx>"
    py = args.python

    def python(file, *argv):
        return [py, str(ROOT / file), *map(str, argv)]

    def blender(file, blend, *argv):
        return [args.blender, "-b", str(blend), "--python-exit-code", "1", "--python", str(ROOT / file), *map(str, argv)]

    worker_common = ["--demo", args.demo, "--asset-plan", str(plan)]
    image_cmd = python("scripts/run_codex_pipeline.py", "images", *worker_common,
                       "--codex", args.codex, "--image-timeout", args.image_timeout)
    if args.codex_model:
        image_cmd += ["--codex-model", args.codex_model]
    if args.reuse_images:
        image_cmd += ["--reuse-images"]
    for reference in args.style_reference:
        image_cmd += ["--style-reference", str(Path(reference).resolve())]
    mesh_python = args.hunyuan_python if args.hunyuan_backend == "local" else py
    mesh_cmd = [mesh_python, str(Path(__file__).resolve()), "meshes", *worker_common,
                "--hunyuan-backend", args.hunyuan_backend, "--hunyuan-server", args.hunyuan_server,
                "--hunyuan-repo", args.hunyuan_repo, "--weights", args.weights]
    if args.skip_existing:
        mesh_cmd.append("--skip-existing")
    candidate_cmd = blender("game_realization/element_placement/extract_placement_candidates.py", scene, "--", "--blend", scene)
    if args.scene_profile:
        candidate_cmd = blender("scripts/blender_candidate_adapter.py", scene, "--", "--blend", scene,
                                "--profile", str(Path(args.scene_profile).resolve()))
    placement_cmd = python("game_realization/element_placement/run_placement_pipeline.py", "--user_prompt", args.prompt)
    if args.scene_profile:
        placement_cmd = python("scripts/placement_context_adapter.py", "--user-prompt", args.prompt,
                               "--profile", str(Path(args.scene_profile).resolve()))
    return [
        ("scene_packet", blender("scene_and_gameplay_planning/extract_default_camera_packet.py", scene),
         [packet / "default_camera_metadata.json", packet / "default_camera_view_grid.png"]),
        ("scene_understanding", python("scene_and_gameplay_planning/run_scene_understanding_vlm.py", "--user_prompt", args.prompt, "--duration_seconds", args.duration),
         [packet / "scene_understanding_default_camera.json"]),
        ("rules", python("scene_and_gameplay_planning/run_game_rule_agent.py", "--user_prompt", args.prompt, "--duration_seconds", args.duration),
         [packet / "game_rule_visual_notes.json", packet / "game_rule_plan.json"]),
        ("placement_candidates", candidate_cmd,
         [packet / "placement_candidates.json"]),
        ("placements", placement_cmd,
         [packet / "gameplay_placement_plan.json"]),
        ("asset_plan", python("game_realization/asset_instantiation/run_asset_realization.py", "--user_prompt", args.prompt), [plan]),
        ("reference_images", image_cmd, [staging / "asset_generation/codex_image_manifest.json"]),
        ("meshes", mesh_cmd, [staging / "asset_generation/asset_generation_manifest.json"]),
        ("stage_assets", blender("game_realization/asset_instantiation/stage_gameplay_assets.py", scene, "--", "--scene_blend", scene), [staged]),
        ("stage_npc", blender("game_realization/asset_instantiation/stage_gameplay_npc.py", staged, "--", "--scene_blend", staged, "--output_blend", staged, "--npc_fbx", npc, "--npc_height_m", args.npc_height, "--npc_yaw_offset_degrees", args.npc_yaw),
         [staging / "npc_staging/npc_staging_report.json"]),
        ("gameplay_path", python("gameplay_logic/build_gameplay_path.py", "--placement_plan", packet / "gameplay_placement_plan.json", "--asset_plan", plan, "--output", path, "--genre", args.genre), [path]),
        ("render", blender("gameplay_logic/stage_gameplay.py", staged, "--", "--scene_blend", staged, "--gameplay_path", path, "--output_dir", output, "--render_video"),
         [output / "gaming_world.blend", output / "gameplay.mp4"]),
    ]


def run_pipeline(args):
    if not 1 <= args.from_stage <= args.to_stage <= 12:
        raise ValueError("Require 1 <= from-stage <= to-stage <= 12")
    stages = stage_commands(args)
    if args.dry_run:
        print(json.dumps([{ "stage": index, "name": name, "command": command, "outputs": list(map(str, outputs))}
                          for index, (name, command, outputs) in enumerate(stages, 1)
                          if args.from_stage <= index <= args.to_stage], ensure_ascii=False, indent=2))
        return
    validate_run_inputs(args)
    staging = Path(get_staging_root(ROOT))
    run_log = staging / "codex" / ("run-" + str(time.time_ns()) + ".json")
    report = {"status": "running", "image_model": "tool-managed-unverified", "stages": [],
              "input": {key: getattr(args, key) for key in
                        ("scene", "prompt", "npc", "demo", "from_stage", "to_stage", "duration",
                         "genre", "scene_profile", "style_reference", "hunyuan_backend", "weights")}}

    def capture(entry, direction):
        try:
            snapshot_stage(staging, run_log, entry, direction)
        except Exception as exc:
            entry.setdefault("report_warnings", []).append(f"{direction} snapshot: {exc}")
            print(f"Report snapshot warning: {exc}", file=sys.stderr)

    def publish():
        write_json(run_log, report)
        try:
            refresh_html_report(staging)
        except Exception as exc:
            print(f"HTML report warning: {exc}", file=sys.stderr)
    env = dict(os.environ, CODE2WORLDS_ROOT=str(ROOT))
    with CodexBridge(backend(args)) as bridge:
        planning_env = bridge.environment(env)
        for index, (name, command, outputs) in enumerate(stages, 1):
            if not args.from_stage <= index <= args.to_stage:
                continue
            entry = {"stage": index, "name": name, "status": "running", "command": command}
            report["stages"].append(entry)
            jobs_before = set((staging / "codex").rglob("prompt.txt"))
            capture(entry, "inputs")
            publish()
            print(f"[{index}/12] {name}", flush=True)
            started = time.time_ns()
            stage_log = run_log.with_name(f"{run_log.stem}-{index:02d}-{name}.log")
            entry["log"] = str(stage_log)
            try:
                with stage_log.open("w") as log:
                    subprocess.run(command, cwd=ROOT, env=planning_env if index in (2, 3, 5, 6) else env,
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
                require_files(outputs)
                if any(path.stat().st_mtime_ns < started for path in outputs):
                    raise RuntimeError(f"Stage {name} did not refresh its expected outputs")
                entry["status"] = "succeeded"
            except BaseException as exc:
                entry.update(status="failed", error=str(exc))
                report["status"] = "failed"
                print(f"Stage failed; inspect {stage_log}", file=sys.stderr)
                raise
            finally:
                entry["elapsed_seconds"] = round((time.time_ns() - started) / 1e9, 3)
                entry["jobs"] = [str(p.parent) for p in sorted(set((staging / "codex").rglob("prompt.txt")) - jobs_before)]
                capture(entry, "outputs")
                publish()
    report["status"] = "succeeded"
    publish()
    print(f"Run record: {run_log}")
    print(f"HTML report: {staging / 'pipeline_report/index.html'}")


def validate_run_inputs(args):
    if not args.scene or not args.prompt:
        raise ValueError("run requires --scene and --prompt (or use --dry-run)")
    require_files([Path(args.scene)])
    if args.from_stage <= 10 <= args.to_stage:
        if not args.npc:
            raise ValueError("Stage 10 requires an animated --npc FBX. Without FBX use --to-stage 9; stage 11 can run separately.")
        require_files([Path(args.npc)])
    if args.from_stage <= 12 <= args.to_stage and args.from_stage > 10:
        # A previous stage 10 may already have embedded an NPC in staged_scene.blend.
        require_files([Path(get_staging_root(ROOT)) / "npc_staging/npc_staging_report.json"])


def doctor(args):
    checks = {"codex": shutil.which(args.codex), "python": Path(args.python).is_file(),
              "blender": shutil.which(args.blender), "hunyuan_python": Path(args.hunyuan_python).is_file(),
              "hunyuan_source": Path(args.hunyuan_repo).is_dir(),
              "shape_weights": (Path(args.weights) / "hunyuan3d-dit-v2-1/model.fp16.ckpt").is_file(),
              "paint_weights": (Path(args.weights) / "hunyuan3d-paintpbr-v2-1").is_dir(),
              "image_model": "Native tool model cannot be pinned or verified by this script"}
    print(json.dumps(checks, indent=2))
    subprocess.run([args.codex, "login", "status"], check=True)


def smoke(args):
    import urllib.request
    with CodexBridge(backend(args, "smoke-chat")) as bridge:
        env = bridge.environment({})
        data = {"messages": [{"role": "user", "content": 'Return exactly {"ok":true,"provider":"codex"}.'}]}
        request = urllib.request.Request(env["OPENAI_BASE_URL"] + "/chat/completions",
                                         data=json.dumps(data).encode(),
                                         headers={"Authorization": "Bearer " + bridge.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=args.codex_timeout + 10) as response:
            result = json.load(response)
        content = json.loads(result["choices"][0]["message"]["content"])
        if content != {"ok": True, "provider": "codex"}:
            raise ValueError(f"Unexpected smoke result: {content}")
        print("Codex planning bridge: OK", flush=True)
    if args.with_image:
        destination = Path(get_staging_root(ROOT)) / "codex" / f"smoke-chest-{time.time_ns()}.png"
        prompt = asset_module().build_reference_prompt({"generation_prompt_en": "A small wooden treasure chest with simple iron bands, closed lid, stylized game prop."})
        result = backend(args, "smoke-images", image=True).generate_image(prompt, destination)
        write_json(destination.with_suffix(".json"), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "smoke", "run", "images", "meshes"])
    parser.add_argument("--demo", default="codex_demo")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-model", help="Planning/agent model; NOT the image model")
    parser.add_argument("--codex-timeout", type=int, default=240)
    parser.add_argument("--image-timeout", type=int, default=900)
    parser.add_argument("--python", default=str(ROOT / ".venv/bin/python"))
    parser.add_argument("--hunyuan-python", default=str(ROOT / ".venv-hunyuan3d/bin/python"))
    parser.add_argument("--blender", default=os.environ.get("BLENDER_BIN", "/home/zjh/.local/opt/blender-4.2.11-linux-x64/blender"))
    parser.add_argument("--hunyuan-backend", choices=["local", "gradio"], default="local")
    parser.add_argument("--hunyuan-server", default="http://127.0.0.1:7860")
    parser.add_argument("--hunyuan-repo", default="/data/models/liveact/3D/Hunyuan3D-2.1-src")
    parser.add_argument("--weights", default="/data/models/liveact/3D/Hunyuan3D-2.1")
    parser.add_argument("--scene")
    parser.add_argument("--scene-profile", help="Optional explicit surface labels for candidate extraction")
    parser.add_argument("--npc")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--genre", choices=["generic", "fps", "tps", "racing", "wingsuit"], default="generic")
    parser.add_argument("--npc-height", type=float, default=1.7)
    parser.add_argument("--npc-yaw", type=float, default=90)
    parser.add_argument("--asset-plan")
    parser.add_argument("--reuse-images", action="store_true")
    parser.add_argument("--style-reference", action="append", default=[], help="Scene image attached to native image generation; repeatable")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--from-stage", type=int, default=1)
    parser.add_argument("--to-stage", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-image", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    os.environ["CODE2GAMES_DEMO_NAME"] = args.demo
    if not get_demo_name():
        raise ValueError("A nonempty --demo is required for output isolation")
    if not 0 < args.codex_timeout < 290:
        raise ValueError("codex-timeout must be below the original VLM HTTP timeout (300 seconds)")
    try:
        {"doctor": doctor, "smoke": smoke, "run": run_pipeline,
         "images": generate_images, "meshes": generate_meshes}[args.command](args)
    except Exception as exc:
        failure = Path(get_staging_root(ROOT)) / "codex" / f"{args.command}-failure-{time.time_ns()}.json"
        write_json(failure, {"command": args.command, "status": "failed", "error": str(exc),
                             "exception": type(exc).__name__})
        print(f"Failure record: {failure}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
