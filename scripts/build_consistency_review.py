"""Build a local comparison gallery using original images without raster editing."""
import argparse
import html
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run = Path(args.run_dir).resolve()
    out = run / "consistency_review"
    out.mkdir(exist_ok=True)
    plan = json.loads((run / "asset_realization/asset_plan.json").read_text())
    placement = json.loads((run / "asset_placement/asset_placement_report.json").read_text())
    images = json.loads((run / "asset_generation/codex_image_manifest.json").read_text())
    context = json.loads((run / "default_camera_packet/placement_context_report.json").read_text())
    conditions = json.loads((out / "render_conditions.json").read_text())
    item = next(x for x in placement["placements"] if x.get("status") == "placed")
    asset = next(x for x in plan["assets"] if x["asset_id"] == item["asset_id"])
    reference = next(x for x in images["assets"] if x["asset_id"] == item["asset_id"])
    center = context["measured_landmark_center"]
    distance = math.hypot(item["world_xyz"][0] - center[0], item["world_xyz"][1] - center[1])
    camera_same = conditions["scene_comparison"][0]["camera_matrix"] == conditions["scene_comparison"][1]["camera_matrix"]
    metrics = {"asset_id": item["asset_id"], "requested_dimensions_m": asset["expected_size_meters"],
               "world_bbox_after_surface_alignment_m": item["bbox_size"],
               "distance_to_measured_bridge_center_m": distance,
               "footprint_radius_m": item["footprint_radius_m"],
               "supported_radius_m": item["candidate_max_supported_footprint_radius_m"],
               "placement_shift_xy_m": item["shift_xy"],
               "support_validation": placement["surface_support_validation"],
               "before_after_camera_matrices_equal": camera_same,
               "requested_scene_references": reference.get("scene_references", []),
               "limitations": ["Native image tool model is not selectable/verified.",
                               "Mesh/reference viewpoints are approximate, not calibrated.",
                               "Support checks do not prove full physics or gameplay consistency.",
                               "No NPC animation or playable game has been produced."]}
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))

    def relative(path):
        return html.escape(os.path.relpath(Path(path).resolve(), out), quote=True)

    def picture(path, caption):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        src = relative(path)
        return f'<figure><a href="{src}" target="_blank"><img src="{src}" loading="lazy"></a><figcaption>{html.escape(caption)}</figcaption></figure>'

    gallery = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>赵沟桥 · 一致性对照 v2</title>
<style>body{{font:16px/1.7 system-ui,sans-serif;background:#f4f3ef;color:#292d29;max-width:1320px;margin:auto;padding:28px}}h1{{margin-bottom:4px}}h2{{margin-top:36px}}.note{{color:#62665e}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.views{{grid-template-columns:repeat(3,minmax(0,1fr))}}figure{{margin:0;background:white;border:1px solid #deded5;border-radius:8px;overflow:hidden}}img{{width:100%;height:360px;object-fit:contain;display:block}}figcaption{{padding:12px}}.facts{{background:white;padding:18px;border-left:4px solid #677860}}a{{color:#365e51}}@media(max-width:750px){{.grid,.views{{grid-template-columns:1fr}}body{{padding:16px}}img{{height:auto}}}}</style>
<h1>赵沟桥 · 一致性对照 v2</h1>
<p class="note">这是可检查的对照证据，不是“一致性评分”。点击图片打开原图。上一轮结果保留。</p>
<div class="facts">箱体目标尺寸：{html.escape(str(asset['expected_size_meters']))} 米；距桥中心：{distance:.2f} 米。<br>
足迹半径 {item['footprint_radius_m']:.3f} 米 / 实测支撑半径 {item['candidate_max_supported_footprint_radius_m']:.3f} 米；装配 XY 偏移 {item['shift_xy']:.3f} 米。<br>
场景前后相机矩阵一致：{camera_same}。两张图均为第 1 帧、1280×720、32 samples，关闭相机景深。<br>
角色动画、开箱交互、完整可玩性未验证；图像模型具体型号不可确认。</div>
<h2>1 · 原场景与新增资产</h2><p>相同镜头与渲染设置；检查背景是否保持、宝箱是否接地、尺度与摆放是否合理。</p><div class="grid">
{picture(out/'scene_before.png', '添加前 · 原赵沟桥场景')}{picture(out/'scene_after.png', '添加后 · 新宝箱位于桥右侧岸边')}</div>
<h2>2 · 参考图与生成的 3D</h2><p>参考图生成任务附带了原场景截图。这里使用近似三分之四视角比较轮廓、箱盖、两条铁箍与中央锁扣；不是精确相机标定。白底 3D 使用独立摄影棚光照，不应将亮度差直接当成材质错误。</p><div class="grid">
{picture(Path(reference['path']), '新生成的参考图 · 以原场景为风格参考')}{picture(out/'mesh_three_quarter.png', '实际 GLB · 白底三分之四视角')}</div>
<h2>3 · 多视角检查</h2><p>侧面、背面和底部有单张参考图未提供的信息，需重点检查结构补全是否合理。</p><div class="grid views">
{picture(out/'mesh_front.png','正面')}{picture(out/'mesh_side.png','侧面')}{picture(out/'mesh_back.png','背面')}{picture(out/'mesh_bottom.png','底部')}</div>
<h2>4 · 实际场景局部前后</h2><p>同一局部相机位置、目标和镜头；此处保留原场景光照。用于检查实际摆放与环境融合。</p><div class="grid">
{picture(out/'closeup_before.png','局部 · 添加前')}{picture(out/'closeup_after.png','局部 · 添加后')}</div>
<h2>产物与记录</h2><p><a href="{relative(run/'staged_scene.blend')}">装配场景 .blend</a> · <a href="{relative(ROOT/asset['expected_glb_path'])}">宝箱 .glb</a> · <a href="metrics.json">可核对的数值</a> · <a href="render_conditions.json">渲染条件</a> · <a href="{relative(run/'asset_generation/codex_image_manifest.json')}">参考图提示词及来源记录</a></p>
</html>'''
    (out / "index.html").write_text(gallery, encoding="utf-8")
    print(out / "index.html")


if __name__ == "__main__":
    main()
