"""Create an offline review page and a self-contained pre-UE delivery archive."""
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'
PACKAGE=OUT/'ue_export'

README='''# 山河驿骑 · UE 前置资产包

这是实际生成、装配并通过 Blender 回读检查的首版资产包。它不是 UE 工程、不是可执行游戏，也没有经过 UE 编译或运行验证。

## 内容

- `Source/gaming_world.blend`：完整装配场景与预录骑行镜头，Blender 4.5.3 保存，贴图已打包。
- `Source/mount_rig.blend`：原地坐骑骨骼与四种动作。自定义四足/骑手共用骨架，不是 UE Mannequin 骨架。
- `Source/song_horse.glb`、`Source/song_rider.glb`：真实 Hunyuan Shape + Paint 生成的原始静态模型。
- `StaticMeshes/*.fbx`：分组的地形、道路、桥、驿站、树林、河面、远山及路标；已烘焙世界坐标，场景重建时都放在原点，缩放 1。
- `SkeletalMeshes/SK_SongMount.fbx`：骑手与马匹组合蒙皮网格，推荐使用这个文件。
- `SkeletalMeshes/SK_Horse.fbx`、`SK_Rider.fbx`：可分开替换的版本，同一套骨架；不要与组合版本重复生成角色。
- `Animations/A_Idle.fbx`、`A_Walk.fbx`、`A_Trot.fbx`、`A_Gallop.fbx`：分别为待机、步行、快步、疾驰原地循环，逐帧烘焙。
- `Textures/`：真实生成的角色贴图与 Blender 烘焙的地面贴图；FBX 内亦嵌入支持的基础颜色贴图。
- `gameplay_config.json`：出生点、近一公里路线、三个顺序检查点与终点、速度及体力参数。它是配置，不是实时控制器。
- `world_manifest.json`、`character_manifest.json`、`validation.json`：场景、骨架、贴图通道和实际验证结果。
- `Previews/`、`ReferenceImages/`、`Reports/`：实渲染画面、视频、原始参考图、规划和模型调用记录。
- `index.html`：离线可视化入口，无需服务。
- `ue_import.py`：可选 UE Editor Python 资产导入脚本，已做 Python 语法检查，但没有在 UE 中执行。
- `SHA256SUMS.json`：包内文件校验和。

## UE 中的接入顺序

1. 新建 UE5 工程。手动导入，或启用 Python Editor Script Plugin / Editor Scripting Utilities 后执行 `ue_import.py`。脚本导入到新的 `/Game/SongRiding`，不创建可玩关卡。
2. 先导入 StaticMeshes，Combine Meshes 开启，每个文件作为一个场景分组；不要把所有 FBX 合成一个资产。所有静态分组放在位置 0、旋转 0、缩放 1。
3. 桥文件包含 `UCX_SM_Bridge_*` 凸碰撞体；桥面由该组碰撞支撑。两个地形和两段道路使用 Complex Collision As Simple，不能给整座山生成一个凸包。
4. 当前树林、驿站、路标是显示资产，未逐个提供阻挡碰撞；按需要在 UE 中补建。河面不能当作可行走地面，水域与边界约束参考配置。
5. 导入 `SK_SongMount.fbx`，新建其自定义 Skeleton；四个动作文件以“仅动画”方式导入并指定这套 Skeleton。不要重定向为人形骨架。原地根骨不带世界位移。
6. 检查单位：马匹头顶约 205 cm、组合骑手约 233 cm。Blender 源文件单位米，源朝向 +X、Z 向上。FBX 使用 Blender 的 -Y Forward / Z Up、单位转换。配置中的预期 UE 位置为 `[x*100, -y*100, z*100]`；在目标 UE 版本先核验出生点与桥两端的轴向，Importer 的 Force Front X Axis 设置会影响方向，不能仅凭 JSON 假定正确。
7. 基础颜色为 sRGB；角色金属度/粗糙度贴图为非颜色数据，G=Roughness、B=Metallic。FBX 不完整保留 glTF 的通道节点，按 `character_manifest.json` 重建 UE 材质。不要把 ORM 当基础颜色。地面 UV 重复采样。
8. 新建关卡，恢复光照与大气。Blender 的天空/雾体积没有包含在静态 FBX 中，参考 world_manifest 的意图重建 SkyAtmosphere / HeightFog / DirectionalLight；不能保证跨引擎逐像素一致。
9. 最后在 UE 中实现 Pawn/移动控制器、跟随相机碰撞、AnimBP 与速度混合、检查点触发、体力、重开、阻挡与水域边界；然后进行实机验证。

## 已验证与限制

`validation.json` 记录的是导出后重新导入 Blender 的检查：网格、基础颜色图片、单根骨架、动作、尺度、蒙皮和路线中心线支撑。它不是 UE 原生导入证明，也不是全地图可达性、马匹扫掠碰撞或相机碰撞证明。

角色来自单视图生成，背面/底部、鬃毛与局部纹理细节存在局限。骨骼按解剖区域自动分配权重，步态为程序化原地循环，没有专业重拓扑、动作捕捉、实时脚部 IK、布料模拟或完整 Control Rig。斜坡上的脚底接触、滑步和局部形变仍需在目标引擎精修。

环境为程序构建的宋风原型，提供大范围山谷与驿道结构，但树木、地表、远山和建筑细节尚未达到写实大作标准。桥来自用户提供的原始场景，水平放大 3 倍、垂直放大 1.5 倍，并额外建立平滑骑行桥面。原场景未修改。

预览视频为 Blender 预录，不是键盘操作录像。Source 场景时间线 30 fps，视频为每两帧采样后编码的 15 fps，约 15 秒。实际模型生成日志、参考图和源码包含在包内，不用概念图冒充实机截图。

## 官方格式参考

- [Epic FBX 静态网格与 UCX 命名](https://dev.epicgames.com/documentation/unreal-engine/fbx-static-mesh-pipeline-in-unreal-engine)
- [Epic FBX 骨骼网格](https://dev.epicgames.com/documentation/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine)
- [Epic FBX 动画](https://dev.epicgames.com/documentation/unreal-engine/fbx-animation-pipeline-in-unreal-engine)
- [UE FbxImportUI](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/FbxImportUI?application_version=5.6)

Epic 文档标明 FBX 管线使用 2020.2。本包由 Blender 4.5.3 自带 FBX 导出器生成，没有使用 Autodesk 2020.2 SDK，因此仍需在目标 UE 版本核验兼容性。
'''

def copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)

def encode_video():
    metadata=json.loads((OUT/'preview_metadata.json').read_text())
    frames=list(range(1,metadata['frames']+1,2))
    paths=[OUT/'previews/frames'/f'ride_{f:04}.png' for f in frames]
    if not all(p.is_file() for p in paths):raise RuntimeError('Incomplete preview sequence; refusing to package a partial video')
    listing=OUT/'previews/video_frames.txt'
    listing.write_text(''.join("file '"+p.name+"'\nduration 0.0666666666667\n" for p in paths))
    # concat filenames resolve next to the list, so use the frames directory.
    frame_list=OUT/'previews/frames/video_frames.txt';copy(listing,frame_list)
    video=OUT/'previews/riding_preview.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',str(frame_list),
        '-r','15','-frames:v',str(len(paths)),'-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
    return video

def main():
    validation=json.loads((PACKAGE/'validation.json').read_text())
    if validation['status']!='passed':raise RuntimeError('Export validation must pass before packaging')
    video=encode_video()
    for src in (OUT/'previews').glob('*.png'):copy(src,PACKAGE/'Previews'/src.name)
    copy(video,PACKAGE/'Previews'/video.name)
    for src in (OUT/'asset_generation/reference_images').glob('*.png'):copy(src,PACKAGE/'ReferenceImages'/src.name)
    for src in (ROOT/'assets/generated_glb/song_riding_20261124').glob('*.glb'):copy(src,PACKAGE/'Source'/src.name)
    copy(OUT/'mount_rig.blend',PACKAGE/'Source/mount_rig.blend')
    copy(ROOT/'scripts/song_riding/ue_import.py',PACKAGE/'ue_import.py')
    for src in (ROOT/'scripts/song_riding').glob('*.py'):copy(src,PACKAGE/'BuildScripts'/src.name)
    for relative in ['game_spec.proposed.json','preview_metadata.json','asset_realization/asset_plan.json','asset_generation/codex_image_manifest.json']:
        copy(OUT/relative,PACKAGE/'Reports'/relative)
    for src in (OUT/'logs').glob('*.log'):copy(src,PACKAGE/'Reports/logs'/src.name)
    for src in (OUT/'codex').rglob('*'):
        if src.is_file() and src.suffix in ('.json','.jsonl','.txt','.log','.png'):copy(src,PACKAGE/'Reports/codex'/src.relative_to(OUT/'codex'))
    for src in (OUT/'previews/iterations').glob('*'):copy(src,PACKAGE/'Reports/iterations'/src.name)
    (PACKAGE/'README.zh-CN.md').write_text(README,encoding='utf-8')
    world=json.loads((PACKAGE/'world_manifest.json').read_text());character=json.loads((PACKAGE/'character_manifest.json').read_text())
    stages=[
        ('01 · Codex 规划','一句话与场景约束 → 宋风驿骑规格','Reports/game_spec.proposed.json'),
        ('02 · 原生生图','马匹与骑手描述 → 两张真实参考图','Reports/asset_generation/codex_image_manifest.json'),
        ('03 · Hunyuan Shape + Paint','参考图 → 两个带 PBR 材质的静态 GLB','Reports/logs/hunyuan.log'),
        ('04 · 世界构建','已有桥梁 + 程序生成河谷、驿道、驿站与林地 → 静态 FBX','world_manifest.json'),
        ('05 · 绑定与动作','静态网格 → 自定义蒙皮骨骼与四个原地循环','character_manifest.json'),
        ('06 · 场景装配','世界 + 骑手 + 路径 → 完整 blend 与非交互视频','Source/gaming_world.blend'),
        ('07 · 导出回读','FBX → Blender 重新导入；路线支撑与蒙皮验证','validation.json'),
        ('08 · UE 导入与运行','尚未执行；资产、脚本与接入说明已准备','README.zh-CN.md')]
    h=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>山河驿骑 · UE 前置交付</title>',
       '<style>body{margin:0;background:#111c23;color:#e6dfce;font:16px/1.7 system-ui}main{max-width:1180px;margin:auto;padding:34px}h1{font-size:40px}h2{margin-top:45px;color:#e6b978}a{color:#9fd0d7}small{color:#aebbc0}.banner{border-left:4px solid #c88d48;padding:16px;background:#203039}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0;background:#1c2a33;padding:12px;border-radius:12px}img,video{width:100%;display:block;border-radius:6px}figcaption{padding:8px 0}details{background:#1c2a33;padding:14px;margin:8px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #34434b;text-align:left}.stats{display:flex;gap:24px;flex-wrap:wrap}.stats b{font-size:26px;color:#e6b978}</style><main>',
       '<small>CODE2GAMES / SONG RIDING / PRE-UE DELIVERY</small><h1>山河驿骑</h1><p>宋风骑手、骏马、石桥与千米驿道。以下均为本次真实生成和 Blender 渲染产物。</p>',
       '<p class="banner">UE 前置资产首版：已导出并通过 Blender 回读。未在 UE 导入、编译或试玩；环境与程序化步态仍属原型质量。</p>',
       '<p><a href="README.zh-CN.md">导入说明与已知限制</a> · <a href="Source/gaming_world.blend">完整 Blender 场景</a> · <a href="ue_import.py">UE 资产导入脚本（未执行）</a> · <a href="SHA256SUMS.json">文件校验和</a></p>',
       f'<div class="stats"><div><b>{len(world["meshes"])}</b> 组静态 FBX</div><div><b>{len(character["bones"])}</b> 骨骼</div><div><b>4</b> 动作片段</div><div><b>{validation["route"]["length_m"]:.0f} m</b> 路线</div></div>',
       '<h2>骑行装配预览</h2><video controls preload="metadata" poster="Previews/riding_bridge.png" src="Previews/riding_preview.mp4"></video><p>预录镜头，15 fps；没有实时玩家输入。坡面脚底接触和步态仍需目标引擎调整。</p>',
       '<h2>分阶段输入与输出</h2><table><tr><th>阶段</th><th>转换</th><th>文件</th></tr>']
    for title,desc,path in stages:h.append(f'<tr><td>{title}</td><td>{desc}</td><td><a href="{path}">查看</a></td></tr>')
    h.append('</table><h2>参考图 → 实际模型 → 骑乘装配</h2><div class="grid">')
    for path,title in [('ReferenceImages/song_horse_Song_Horse.png','生图输入：马匹'),('ReferenceImages/song_rider_Song_Rider.png','生图输入：宋风骑手'),('Previews/mount_hero.png','实际带骨骼组合模型'),('Previews/mount_side.png','侧视与骑乘位置')]:
        h.append(f'<figure><a href="{path}"><img loading="lazy" src="{path}"></a><figcaption>{title}</figcaption></figure>')
    h.append('</div><h2>世界与路线</h2><div class="grid">')
    for name,title in [('world_overview','河谷与远山'),('valley_route','驿道与驿站'),('riding_start','道路上的骑乘尺度'),('riding_bridge','过桥镜头')]:
        h.append(f'<figure><a href="Previews/{name}.png"><img loading="lazy" src="Previews/{name}.png"></a><figcaption>{title}</figcaption></figure>')
    h.append('</div><h2>疾驰循环四帧</h2><div class="grid">')
    for frame in [1,7,13,19]:h.append(f'<figure><img loading="lazy" src="Previews/gallop_{frame:02}.png"><figcaption>第 {frame} 帧 · 程序化骨骼动作</figcaption></figure>')
    h.append('</div><h2>验证结果与适用范围</h2>')
    h.append(f'<p>{len(validation["fbx"])} 个 FBX 回读检查通过；501 个路线中心点检查通过，最大采样坡度 {validation["route"]["max_grade_degrees"]:.1f}°。这不代表 UE 碰撞、全图可达性或视觉质量已经验收。</p>')
    h.append('<details><summary>实际验证 JSON</summary><pre>'+html.escape(json.dumps(validation,ensure_ascii=False,indent=2))+'</pre></details>')
    h.append('<h2>文件与可替换边界</h2><p>静态环境、原始 GLB、组合/分离角色、原地动作、路线配置分别交付。使用自己的模型时需保持尺寸、坐标与骨架/动作接口，或重新绑定。</p><ul>')
    for path in sorted(PACKAGE.rglob('*')):
        if path.is_file() and path.suffix in ('.fbx','.glb','.json') and 'Reports' not in path.parts:
            rel=path.relative_to(PACKAGE).as_posix();h.append(f'<li><a href="{html.escape(rel)}">{html.escape(rel)}</a> · {path.stat().st_size/1024/1024:.2f} MB</li>')
    h.append('</ul><h2>当前视觉限制</h2><p>人物和马匹为单图生成，细节与背面不能视为精确历史还原；场景地表、植被、远山采用程序化原型美术。骑行动作不是动捕。UE 中仍需重建材质通道、大气、碰撞与实时玩法。</p></main></html>')
    (PACKAGE/'index.html').write_text(''.join(h),encoding='utf-8')
    hashes={p.relative_to(PACKAGE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json' and not p.name.endswith('.blend1')}
    (PACKAGE/'SHA256SUMS.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2))
    archive=OUT/'SongRiding_UE_Preproduction.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for path in sorted(PACKAGE.rglob('*')):
            if path.is_file() and not path.name.endswith('.blend1'):z.write(path,'SongRiding/'+path.relative_to(PACKAGE).as_posix())
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'html':str(PACKAGE/'index.html'),'hashed_files':len(hashes)},ensure_ascii=False))

if __name__=='__main__':main()
