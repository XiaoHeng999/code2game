"""Supply scene-semantic distances to the existing placement selector, without coordinates."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game_realization/element_placement"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-prompt", required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    profile = json.loads(Path(args.profile).read_text())
    spec = importlib.util.spec_from_file_location("original_placement", ROOT / "game_realization/element_placement/run_placement_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidates = module.load_json(module.packet_path("placement_candidates.json"))["candidates"]
    anchor = profile.get("placement_context")
    center = None
    if anchor:
        points = [x["world_xyz"] for x in candidates if x.get("hit_object", "").startswith(anchor["object_prefix"])]
        if not points:
            raise ValueError("No measured candidates matched placement-context landmark")
        center = [(min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3)]
    original = module.candidate_for_llm

    def enriched(candidate):
        result = original(candidate)
        result["hit_object"] = candidate.get("hit_object")
        result["measured_support_radius_m"] = candidate.get("max_supported_footprint_radius_m")
        if center:
            distance = math.hypot(candidate["world_xyz"][0] - center[0], candidate["world_xyz"][1] - center[1])
            result["landmark_context"] = {"landmark": anchor["label"], "distance_xy_m": round(distance, 3),
                                           "within_requested_region": distance <= anchor["max_distance_xy_m"]}
        return result

    module.candidate_for_llm = enriched
    prompt = args.user_prompt
    if anchor:
        prompt += (f"\nThe requested region is within {anchor['max_distance_xy_m']} meters horizontally of the "
                   f"measured {anchor['label']} center. Both spawn and objective must satisfy within_requested_region=true. "
                   "Use the explicit surface name and measured support radius. If no valid placements exist, report unusable. "
                   "Do not substitute far-away scenery. Do not invent or change coordinates.")
    result = module.main(prompt)
    if result.get("ok") and anchor:
        plan = module.load_json(module.packet_path("gameplay_placement_plan.json"))
        for item in plan["placement_plan"]["elements"]:
            if math.hypot(item["world_xyz"][0] - center[0], item["world_xyz"][1] - center[1]) > anchor["max_distance_xy_m"]:
                Path(module.packet_path("gameplay_placement_plan.json")).unlink()
                raise ValueError("Selected placement violates explicit landmark region")
    module.write_json(module.packet_path("placement_context_report.json"), {
        "profile": args.profile, "measured_landmark_center": center,
        "context": anchor, "ok": result.get("ok", False),
    })
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Placement failed"))


if __name__ == "__main__":
    main()
