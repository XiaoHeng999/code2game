"""Render verifiable comparison views; run with background Blender, never saves input blends."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def configure(path, width=960, height=720, studio=False):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(path)
    if studio:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
    bpy.ops.render.render(write_still=True)


def camera_at(location, target, name="CONSISTENCY_CAMERA", lens=50):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = name
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = lens
    camera.data.dof.use_dof = False
    bpy.context.scene.camera = camera
    return camera


def mesh_bounds(objects):
    corners = [obj.matrix_world @ Vector(c) for obj in objects if obj.type == "MESH" for c in obj.bound_box]
    if not corners:
        raise ValueError("No mesh geometry")
    low = Vector([min(p[i] for p in corners) for i in range(3)])
    high = Vector([max(p[i] for p in corners) for i in range(3)])
    return low, high


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--staged", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--placement-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads(Path(args.placement_report).read_text())
    placed = next(p for p in report["placements"] if p.get("status") == "placed")
    target = Vector(placed["bbox_center"])
    review = {"note": "Reference and mesh viewpoints are approximate matches, not calibrated identical cameras.",
              "scene_comparison": [], "mesh_views": []}

    # Both before/after pairs use the same camera transforms, frame and settings.
    for label, blend in [("before", args.source), ("after", args.staged)]:
        bpy.ops.wm.open_mainfile(filepath=str(Path(blend).resolve()))
        scene = bpy.context.scene
        scene.frame_set(1)
        scene.camera = bpy.data.objects["Orbit camera"]
        scene.camera.data.dof.use_dof = False
        configure(output / f"scene_{label}.png", 1280, 720)
        review["scene_comparison"].append({"label": label, "camera_matrix": [list(r) for r in scene.camera.matrix_world],
                                            "frame": 1, "resolution": [1280, 720], "samples": 32})
        camera = camera_at(target + Vector((2.0, -3.4, 1.8)), target, lens=48)
        configure(output / f"closeup_{label}.png")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
    low, high = mesh_bounds(bpy.context.scene.objects)
    center = (low + high) / 2
    size = max(high - low)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("WhiteStudio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    for offset, power in [((2, -3, 4), 250), ((-3, -1, 2), 130), ((1, 3, 3), 180)]:
        bpy.ops.object.light_add(type="AREA", location=center + Vector(offset) * size)
        light = bpy.context.object
        light.data.energy = power * size * size
        light.data.size = 3 * size
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    views = {"three_quarter": (1.7, -2.8, 1.5), "front": (0, -3.2, 0.45),
             "side": (3.2, 0, 0.45), "back": (0, 3.2, 0.45), "bottom": (0, -0.01, -3.2)}
    for name, offset in views.items():
        camera = camera_at(center + Vector(offset) * size, center, lens=55)
        configure(output / f"mesh_{name}.png", 768, 768, studio=True)
        review["mesh_views"].append({"view": name, "camera_matrix": [list(r) for r in camera.matrix_world]})
        bpy.data.objects.remove(camera, do_unlink=True)
    review["mesh_bounds_native"] = [list(low), list(high)]
    (output / "render_conditions.json").write_text(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()
