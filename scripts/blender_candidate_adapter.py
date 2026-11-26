"""Optional scene-specific semantic overrides; original extractor stays unchanged."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]


def volume_only(obj):
    if obj.type != "MESH" or not obj.material_slots:
        return False
    for slot in obj.material_slots:
        material = slot.material
        if material is None or not material.use_nodes:
            return False
        outputs = [n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
        if not outputs or any(n.inputs["Surface"].is_linked or not n.inputs["Volume"].is_linked for n in outputs):
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    profile = json.loads(Path(args.profile).read_text())
    overrides = profile.get("surface_overrides", [])
    for rule in overrides:
        if not rule.get("object_prefix") or rule.get("surface_type") not in {"ground", "rock", "water", "vegetation", "unknown"}:
            raise ValueError("Invalid surface override")
    file = ROOT / "game_realization/element_placement/extract_placement_candidates.py"
    spec = importlib.util.spec_from_file_location("original_candidate_extractor", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_classify = module.classify_surface
    original_load = module.ensure_target_blend_loaded
    audit = {"profile": str(Path(args.profile).resolve()), "surface_overrides": overrides, "excluded_volume_objects": []}

    def classify(obj, normal):
        for rule in overrides:
            if obj and obj.name.startswith(rule["object_prefix"]):
                return rule["surface_type"]
        return original_classify(obj, normal)

    def load(path):
        result = original_load(path)
        if profile.get("exclude_volume_only_from_raycast"):
            for obj in bpy.context.scene.objects:
                if volume_only(obj):
                    obj.hide_viewport = True
                    audit["excluded_volume_objects"].append(obj.name)
            bpy.context.view_layer.update()
        return result

    module.classify_surface = classify
    module.ensure_target_blend_loaded = load
    sys.argv = [str(file), "--", "--blend", args.blend]
    try:
        module.main()
    finally:
        path = Path(module.PACKET_DIR) / "candidate_adapter_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
