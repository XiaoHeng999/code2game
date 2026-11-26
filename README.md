# Code2Games

Code2Games 是一个将已有 3D 场景、自然语言游戏意图和角色资产组合成可运行游戏世界与玩法视频的自动化流程。项目以 Blender 为场景执行与渲染核心，通过视觉语言模型完成场景理解和玩法规划，并使用 Hunyuan3D 生成或补充游戏资产。

## 功能概览

输入以下内容后，系统可以自动完成：

- 分析 Blender 场景和默认相机视角；
- 根据自然语言描述生成游戏规则和玩法目标；
- 在场景中提取可用位置并规划资产摆放；
- 生成或复用游戏资产，并将资产导入 Blender；
- 导入带动画的人形 NPC；
- 生成游戏路径、角色运动和跟随相机；
- 输出最终的 Blender 游戏世界文件和 gameplay 视频。

## 环境要求

建议使用 Linux 或 macOS，并准备以下软件和服务：

- Python 3.11；
- Blender 4.2 或兼容版本，并确保命令行可以执行 `blender`；
- Hunyuan3D 2.1，用于生成 GLB 资产；
- DashScope 兼容接口，用于当前版本的视觉理解和资产参考图生成；
- 一个已经生成好的 Blender 场景文件（`.blend`），场景中应包含可用的默认相机；
- 一个带骨骼和动画的人形 FBX 文件，用作游戏 NPC。

Blender 自带 `bpy` 和 `mathutils`，不需要也不应使用 pip 单独安装这两个包。

## 安装

```bash
git clone https://github.com/XiaoHeng999/code2game.git
cd code2game

conda create -n code2games python=3.11
conda activate code2games
pip install -r requirements.txt
```

如果不使用 Conda，也可以使用 Python 3.11 的虚拟环境：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Hunyuan3D

Hunyuan3D 支持两种接入方式。

使用 Gradio 服务时：

```bash
export HUNYUAN_BACKEND="gradio"
export HUNYUAN_SERVER="http://127.0.0.1:8080"
```

使用本地 Hunyuan3D 安装时：

```bash
export HUNYUAN_BACKEND="local"
export HUNYUAN3D_REPO="/path/to/Hunyuan3D-2.1"
export HUNYUAN3D_MODEL_PATH="tencent/Hunyuan3D-2.1"
```

Hunyuan3D 本身的 PyTorch、CUDA 和模型依赖需要按照其安装方式单独配置。

## 配置 API 和运行环境

运行前配置 DashScope 和模型信息：

```bash
export DASHSCOPE_API_KEY="your_api_key"
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export CODE2GAMES_VLM_MODEL="qwen3-vl-plus"
```

可选的可执行文件配置：

```bash
export PYTHON_BIN="python"
export BLENDER_BIN="blender"
```

不要把 API Key 直接写入代码或提交到 Git 仓库。

## 准备输入文件

完整流程需要两个输入文件：

```text
scene.blend                    # 已有的 3D 场景，必须存在默认相机
assets/mixamo/mixamo_run.fbx   # 带骨骼和动画的人形 NPC
```

NPC 可以使用 Mixamo 等工具准备。建议下载带皮肤、带动画的 FBX；如果只有静态模型，需要先完成自动绑定和行走/奔跑动画制作。

## 一键运行

完整流程由 `scripts/generate_gaming_world.sh` 驱动：

```bash
bash scripts/generate_gaming_world.sh \
  "/path/to/scene.blend" \
  "Create a third-person monster hunt in a dark forest. Track the creature, defeat it, and claim the trophy." \
  "assets/mixamo/mixamo_run.fbx" \
  "monster_hunt"
```

参数格式：

```text
generate_gaming_world.sh <scene.blend> <game-intent-prompt> <animated-npc.fbx> [game-name]
```

`game-name` 是可选参数，用于隔离不同游戏的输出目录。脚本会自动检查 Blender、Python、输入文件、API Key、模型名称以及 Hunyuan3D 后端配置。

## 输出文件

当游戏名为 `monster_hunt` 时，主要输出位于：

```text
output/game_staging/monster_hunt/
├── default_camera_packet/       # 场景分析、规则、候选点和摆放方案
├── asset_realization/           # 游戏资产规划结果
├── asset_generation/            # 参考图、生成日志和资产清单
├── asset_placement/             # 资产摆放报告
├── npc_staging/                 # NPC 导入和摆放报告
├── staged_scene.blend           # 完成资产和 NPC 导入的中间场景
├── gameplay_path/               # 游戏路径和动作规划
└── gameplay_output/
    ├── gaming_world.blend       # 最终游戏世界
    └── gameplay.mp4             # 玩法视频
```

生成的 GLB 资产默认保存在：

```text
assets/generated_glb/<game-name>/
```

## 整体框架与执行流程

项目按照“场景理解 → 玩法规划 → 资产实现 → Blender 执行 → 动作与渲染”的顺序运行：

```text
场景 .blend + 游戏意图 + NPC FBX
              │
              ▼
┌─────────────────────────────┐
│ 1. 提取默认相机和场景信息     │
│ 2. VLM 场景理解               │
│ 3. 生成游戏规则和玩法目标     │
│ 4. 提取场景中的候选位置       │
│ 5. 生成受场景约束的摆放方案   │
│ 6. 规划游戏资产               │
│ 7. 生成或复用 GLB 资产         │
│ 8. 将资产导入 Blender          │
│ 9. 导入并摆放动画 NPC          │
│10. 生成游戏路径               │
│11. 生成动作、相机和视频        │
└─────────────────────────────┘
              │
              ▼
       gaming_world.blend + gameplay.mp4
```

对应的代码模块如下：

```text
scene_and_gameplay_planning/  # 场景理解、相机数据和玩法规则规划
game_realization/             # 位置选择、资产生成和 Blender 场景组装
gameplay_logic/               # 游戏路径、角色动作、相机和视频渲染
shared_representation/        # 各阶段共享的数据结构、路径和约束
scripts/                      # 一键流水线、兼容适配和检查工具
```

## 常用运行选项

```bash
# 复用已经存在且有效的 GLB 资产
export CODE2GAMES_SKIP_EXISTING_ASSETS=1

# 设定规划时长，默认 30 秒
export CODE2GAMES_DURATION_SECONDS=30

# 选择玩法类型：generic、fps、tps、racing、wingsuit
export CODE2GAMES_GENRE="tps"

# 生成预览帧，并添加玩法事件特效
export CODE2GAMES_RENDER_PREVIEWS=1
export CODE2GAMES_ADD_EVENTS=1

# 调整 NPC 高度和模型朝向
export CODE2GAMES_NPC_HEIGHT_M=1.7
export CODE2GAMES_NPC_YAW_OFFSET_DEGREES=90
```

查看脚本参数说明：

```bash
bash scripts/generate_gaming_world.sh
```

## 常见问题

### 找不到 Blender

确认 Blender 已安装，并检查：

```bash
which blender
blender --version
```

如果 Blender 不在 PATH 中，设置完整路径：

```bash
export BLENDER_BIN="/path/to/blender"
```

### 找不到输入场景或 NPC

建议使用绝对路径，或者确认相对路径是相对于执行命令时所在目录解析的：

```bash
ls -lh /path/to/scene.blend
ls -lh assets/mixamo/mixamo_run.fbx
```

### 资产生成失败

优先检查 `DASHSCOPE_API_KEY`、`CODE2GAMES_VLM_MODEL` 和 Hunyuan3D 服务是否可访问。若资产已经生成过，可以设置 `CODE2GAMES_SKIP_EXISTING_ASSETS=1` 复用已有 GLB，减少重复生成。

## 参考

本项目的整体思路和部分基础实现参考了原本的 Code2Games 仓库。
