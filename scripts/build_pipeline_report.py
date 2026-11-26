"""Offline HTML input/output reports. No inference, web dependencies or original pipeline edits."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
P = "default_camera_packet/"
# Explicit stage contracts, rather than inferring success from files that happen to exist.
STAGES = [
    ("场景采集", [], [P+"default_camera_*"]),
    ("场景理解", [P+"default_camera_view*.png", P+"default_camera_metadata.json"], [P+"scene_understanding*"]),
    ("玩法规则", [P+"scene_understanding_default_camera.json", P+"default_camera_view*.png"], [P+"game_rule*"]),
    ("候选位置", [P+"default_camera_metadata.json"], [P+"placement_candidates*", P+"candidate_adapter_report.json"]),
    ("位置规划", [P+"placement_candidates.json", P+"game_rule_plan.json"], [P+"gameplay_placement*", P+"placement_context_report.json"]),
    ("资产规划", [P+"gameplay_placement_plan.json", P+"game_rule_plan.json"], ["asset_realization/*"]),
    ("参考图生成", ["asset_realization/asset_plan.json"], ["asset_generation/codex_image_manifest.json", "asset_generation/reference_images/*"]),
    ("3D 生成", ["asset_realization/asset_plan.json", "asset_generation/reference_images/*"], ["asset_generation/asset_generation_manifest.json", "asset_generation/hunyuan_raw/*"]),
    ("场景装配", ["asset_realization/asset_plan.json", P+"gameplay_placement_plan.json"], ["staged_scene.blend", "asset_placement/**/*.json", "asset_placement/**/*.png"]),
    ("角色装配", ["staged_scene.blend"], ["npc_staging/**/*", "staged_scene.blend"]),
    ("路径编排", [P+"gameplay_placement_plan.json", "asset_realization/asset_plan.json"], ["gameplay_path/*"]),
    ("动画渲染", ["staged_scene.blend", "gameplay_path/gameplay_path.json"], ["gameplay_output/**/*"]),
]
SMALL = {".json", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
CSS = """body{font:16px/1.65 system-ui,sans-serif;color:#25322e;background:#f2f4f1;margin:0}main{max-width:1320px;margin:auto;padding:24px}a{color:#236a62}nav{display:flex;gap:12px;flex-wrap:wrap;position:sticky;top:0;background:#f2f4f1;padding:10px;z-index:2}section,article{background:white;padding:20px;margin:18px 0;border:1px solid #d7dfd8;border-radius:10px}h1,h2,h3{line-height:1.3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.file{border:1px solid #dce3df;padding:12px;overflow:hidden;border-radius:6px}img{display:block;width:100%;height:250px;object-fit:contain;background:#f7f7f5}video{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:460px;overflow:auto;font:13px/1.6 monospace;background:#f4f6f4;padding:12px}small,.muted{color:#65736c}details{margin:12px 0}.badge{border-radius:16px;background:#e6eee8;padding:3px 12px}.failed{background:#ffe1df}.running{background:#fff0c9}input{padding:12px;width:min(90%,600px);font:inherit}code{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #ddd}@media(max-width:650px){main{padding:10px}section{padding:12px}}"""


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def files(run, patterns):
    return sorted({p.resolve() for pattern in patterns for p in run.glob(pattern) if p.is_file()})


def stage_files(run, number, direction, command=()):
    result = files(run, STAGES[number-1][1 if direction == "inputs" else 2])
    if direction == "inputs":
        for flag in ("-b", "--scene_blend", "--npc_fbx", "--profile", "--style-reference"):
            for i, arg in enumerate(command[:-1]):
                if arg == flag and Path(command[i+1]).is_file():
                    result.append(Path(command[i+1]).resolve())
    if (direction == "outputs" and number == 8) or (direction == "inputs" and number == 9):
        plan = read(run / "asset_realization/asset_plan.json", {})
        for asset in plan.get("assets", []):
            path = ROOT / asset.get("expected_glb_path", "__missing__")
            if path.is_file():
                result.append(path.resolve())
    return sorted(set(result))


def snapshot(run, record, entry, direction):
    """Immutable small-file snapshots; large binaries have path/hash, not misleading copies."""
    destination = run / "pipeline_report/archive" / record.stem / f"{entry['stage']:02d}" / direction
    destination.mkdir(parents=True, exist_ok=True)
    captured = []
    for path in stage_files(run, entry["stage"], direction, entry.get("command", [])):
        item = {"source": str(path), "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns}
        with path.open("rb") as f:
            item["sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
        if path.suffix.lower() in SMALL and item["bytes"] <= 32 * 1024 * 1024:
            target = destination / (hashlib.sha256(str(path).encode()).hexdigest()[:12] + "_" + path.name)
            if not target.exists():
                shutil.copy2(path, target)
            item["snapshot"] = str(target)
        captured.append(item)
    entry[direction] = captured


def page(title, content):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style><main><h1>'+html.escape(title)+'</h1>'+content+"</main></html>"


class Renderer:
    def __init__(self, output):
        self.output = output

    def url(self, path):
        return quote(os.path.relpath(Path(path).resolve(), self.output.parent), safe="/")

    def link(self, path, label=None):
        return f'<a href="{self.url(path)}">{html.escape(label or Path(path).name)}</a>'

    def artifact(self, path, label=None):
        path = Path(path)
        label = label or path.name
        if not path.is_file():
            return '<div class="file muted">缺失：'+html.escape(str(path))+'</div>'
        suffix = path.suffix.lower()
        body = self.link(path, label)
        src = self.url(path)
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            body += f'<a href="{src}"><img loading="lazy" src="{src}" alt="{html.escape(label, quote=True)}"></a>'
        elif suffix in {".mp4", ".webm"}:
            body += f'<video controls preload="none" src="{src}"></video>'
        elif suffix in {".json", ".jsonl", ".md", ".txt", ".log"}:
            with path.open(errors="replace") as f:
                text = f.read(24001)
            if suffix == ".json" and len(text) <= 24000:
                try:
                    text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
                except ValueError:
                    pass
            clipped = len(text) > 24000
            body += '<details><summary>展开内容'+('（预览截断；完整内容见文件）' if clipped else '')+'</summary><pre>'+html.escape(text[:24000])+'</pre></details>'
        else:
            body += '<p class="muted">二进制产物：下载或用对应软件打开。'+str(round(path.stat().st_size/1048576, 2))+' MiB</p>'
        return '<div class="file">'+body+'</div>'

    def artifacts(self, paths):
        return '<div class="grid">'+''.join(self.artifact(p) for p in paths)+'</div>' if paths else '<p class="muted">没有记录或没有产物。</p>'

    def captured(self, items):
        result = []
        for item in items:
            path = item.get("snapshot", item["source"])
            note = "已归档快照" if "snapshot" in item else "外部/大文件链接，可能随后改变；记录哈希供核对"
            result.append(self.artifact(path, Path(item["source"]).name) + '<small>'+note+' · SHA-256 <code>'+html.escape(item["sha256"])+'</code></small>')
        return ''.join(result) or '<p class="muted">本阶段未记录文件。</p>'


def build_report(run):
    run = Path(run).resolve()
    output = run / "pipeline_report/index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    r = Renderer(output)
    records = [(p, read(p, {})) for p in sorted((run/"codex").glob("run-*.json"))]
    content = '<p>逐阶段输入 / 输出 · 每次模型调用 · 原图与原始数据。可离线打开；所有内容来自本地记录，不重新调用模型。</p>'
    content += '<nav><a href="#current">阶段产物</a><a href="#runs">执行历史</a><a href="#calls">模型调用</a>'+r.link(run.parent/"pipeline_runs.html", "所有实验")+'</nav>'
    content += '<p class="muted">阶段产物区展示当前文件；旧运行没有快照时不能证明它是当次输出。新运行保存文本和图片快照，大型 blend/GLB/视频只记录链接和哈希。失败阶段的执行后快照可能含旧文件或不完整产物。成功状态不等于视觉一致或完整可玩。</p>'
    if (run/"consistency_review/index.html").is_file():
        content += '<p>'+r.link(run/"consistency_review/index.html", "打开同机位一致性对照")+'</p>'
    content += '<section id="current"><h2>阶段产物 · 当前目录</h2>'
    for number, (name, _, _) in enumerate(STAGES, 1):
        entries = [e for _, rec in records for e in rec.get("stages", []) if e.get("stage") == number]
        status = entries[-1].get("status", "unknown") if entries else "无执行记录"
        cmd = entries[-1].get("command", []) if entries else []
        content += f'<details><summary>{number:02d} · {name} · {html.escape(status)}</summary><h3>输入文件</h3>'
        content += r.artifacts(stage_files(run, number, "inputs", cmd))+'<h3>输出文件</h3>'+r.artifacts(stage_files(run, number, "outputs"))+'</details>'
    content += '</section>'
    review = files(run, ["consistency_review/*.png"])
    if review:
        content += '<section><h2>实际渲染 · 当前版本</h2>'+r.artifacts(review)+'</section>'
    content += '<section id="runs"><h2>每次执行记录</h2>'
    for record, data in records:
        status = data.get("status", "unknown")
        content += '<article><h3>'+html.escape(record.stem)+' <span class="badge '+html.escape(status, quote=True)+'">'+html.escape(status)+'</span></h3>'+r.link(record, "完整运行记录")
        if data.get("input"):
            content += '<details><summary>本次输入配置</summary><pre>'+html.escape(json.dumps(data["input"], ensure_ascii=False, indent=2))+'</pre></details>'
        for entry in data.get("stages", []):
            content += '<details><summary>'+html.escape(str(entry.get("stage"))+" · "+entry.get("name", "")+" · "+entry.get("status", "unknown"))+'</summary>'
            content += '<h4>执行参数（含用户提示词）</h4><pre>'+html.escape(json.dumps(entry.get("command", []), ensure_ascii=False, indent=2))+'</pre>'
            if entry.get("error"):
                content += '<pre>'+html.escape(entry["error"])+'</pre>'
            if entry.get("report_warnings"):
                content += '<pre>'+html.escape(json.dumps(entry["report_warnings"], ensure_ascii=False))+'</pre>'
            if "elapsed_seconds" in entry:
                content += '<p>执行耗时：'+str(entry["elapsed_seconds"])+' 秒</p>'
            for direction, title in [("inputs", "执行前输入快照"), ("outputs", "执行后输出快照")]:
                content += '<h4>'+title+'</h4>'+(r.captured(entry[direction]) if direction in entry else '<p class="muted">旧记录未采集快照；请参考当前产物区，不应视为该次运行的历史输出。</p>')
            if entry.get("log"):
                content += r.artifact(entry["log"])
            if "jobs" in entry:
                content += '<p>关联模型调用：'+(' · '.join('<a href="#job-'+html.escape(Path(p).name, quote=True)+'">'+html.escape(Path(p).name)+'</a>' for p in entry["jobs"]) or '无')+'</p>'
            content += '</details>'
        content += '</article>'
    content += '</section><section id="calls"><h2>每次模型调用</h2><p>旧调用按文件时间排序，不猜测其所属阶段；新运行在执行记录中保存关联。输入附件不等于已审计模型内部的使用方式。</p><input id="search" placeholder="搜索提示词或返回内容…">'
    jobs = sorted({p.parent for p in (run/"codex").rglob("prompt.txt")}, key=lambda p:(p/"prompt.txt").stat().st_mtime_ns)
    image_manifest = read(run/"asset_generation/codex_image_manifest.json", {})
    legacy_refs = {str(Path(a["job"]).resolve()): a.get("scene_references", [])
                   for a in image_manifest.get("assets", []) if a.get("job")}
    for job in jobs:
        stamp = datetime.fromtimestamp((job/"prompt.txt").stat().st_mtime, timezone.utc).isoformat()
        content += '<article class="job" id="job-'+html.escape(job.name, quote=True)+'"><h3>'+html.escape(job.parent.name+" / "+job.name)+'</h3><small>提示词文件时间 UTC：'+stamp+'</small><h4>输入提示词与附件</h4>'
        content += r.artifact(job/"prompt.txt")+r.artifacts(sorted(job.glob("input-*")))
        metadata = read(job/"invocation.json", {})
        references = metadata.get("images", legacy_refs.get(str(job), []))
        external_refs = [Path(p) for p in references if not Path(p).is_relative_to(job)]
        if external_refs:
            content += '<p class="muted">外部参考附件（当前路径，非独立调用快照）</p>'+r.artifacts(external_refs)
        content += '<h4>输出</h4>'+r.artifact(job/"response.json")+r.artifacts(sorted(job.glob("reference.*")))
        content += '<details><summary>调用事件与诊断</summary>'+r.artifacts([p for p in [job/"events.jsonl", job/"stderr.log", job/"invocation.json"] if p.exists()])+'</details></article>'
    if not jobs:
        content += '<p>未找到独立模型调用记录。</p>'
    content += '</section><script>document.getElementById("search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll(".job").forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(q))})</script>'
    output.write_text(page(run.name+" · 输入输出报告", content), encoding="utf-8")
    return output


def build_index(root):
    output = root/"pipeline_runs.html"
    r = Renderer(output)
    body = '<p>每个实验有独立的阶段输入输出、执行历史与模型调用记录。</p>'
    for report in sorted(root.glob("*/pipeline_report/index.html")):
        body += '<section><h2>'+r.link(report, report.parent.parent.name)+'</h2></section>'
    output.write_text(page("Code2Games · 实验记录", body), encoding="utf-8")
    return output


def refresh(run):
    output = build_report(run)
    build_index(Path(run).resolve().parent)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all:
        for run in sorted((ROOT/"output/game_staging").iterdir()):
            if run.is_dir() and (run/"codex").is_dir():
                print(refresh(run))
    elif args.run_dir:
        print(refresh(args.run_dir))
    else:
        parser.error("Choose --run-dir or --all")
