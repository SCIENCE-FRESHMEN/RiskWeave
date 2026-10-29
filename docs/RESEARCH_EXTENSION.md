# 选择性重规划原型与复现说明

本轮在原项目上新增了可运行的结构化调度原型、合成离散实验和 ROS 决策预览接口，并修复了已确认的提供商调用问题。来源与上游作者见 [ORIGIN.md](ORIGIN.md)。本文件与结果报告不宣称已经完成原论文复现或验证了学术新颖性。

## 现在可以运行的内容

在 Windows 项目根目录运行：

```powershell
.\run_research.ps1 -Mode verify
.\run_research.ps1 -Mode replay
.\run_research.ps1 -Mode benchmark -Episodes 50 -SeedStart 1000
```

脚本优先使用当前用户已有的 Codex Python 运行时，也支持通过 `RISKWEAVE_PYTHON` 指定 Python 3.10+。它不安装依赖、不调用付费模型、不覆盖已有实验输出。Linux 或其他 Python 环境可直接执行：

```bash
python3 -B tools/check_selective_replanning.py
python3 -B tools/run_selective_replay.py
python3 -B tools/run_selective_benchmark.py --episodes 50 --seed-start 1000 --output artifacts/new-run
```

上述新研究模块仅依赖 Python 标准库。原有 GUI、机器人节点和云模型调用另需 ROS 与相应依赖。

## 方法定义与边界

实现位于 `riskweave/riskweave_console/riskweave_console/selective/core.py`。

1. **能力不确定性。** 每个机器人—技能对使用 Beta(α, β) 描述成功率。只接受明确的布尔成功/失败观测；缺失信息不自动补成成功。更新时将超过均匀先验的证据按配置折扣，以适应能力变化。这个折扣估计是启发式模型，不是已校准的变点检测器。
2. **风险评分。** 成功率均值 μ=α/(α+β)，后验方差为 αβ/[(α+β)²(α+β+1)]。用单侧 Cantelli 界构造失败率评分 `q=min(1, 1−μ+sqrt(var·(1−δ)/δ))`，再乘以配置中的“失败后发生严重后果”的条件概率。调度约束为已保留的尝试风险加当前波风险不超过预算。已完成、失败和中断的尝试不退还风险预算。这些界依赖后验与后果模型，不能解释成真实机器人全程安全保证，也没有证明自适应多次决策下的联合校准。
3. **任务价值。** 单个分配的预期净价值为 `value·μ − failure_loss·(1−μ) − execution_cost`；切换已有任务另付切换代价。先最大化当前波可安排的必需目标/必需前置目标数量，再最大化净价值。
4. **选择性触发。** 先使用忽略机器人冲突和联合风险约束的松弛价值上界，判断可能收益是否超过规划、通信与延迟代价。无可用能力时不反复求空方案；只剩低价值可选目标且收益不能覆盖规划费用时直接放弃。必需目标不会按价值低而主动舍弃。
5. **部分完成。** 显式区分完成、失败、过期、放弃和前置条件导致不可达。容量暂时不足时延后，不能将未执行任务算成完成；已完成目标不能重复计分。
6. **紧急事件。** 模型中的紧急停止独立于规划预算，并保持锁存，直至收到明确恢复事件。ROS 预览接口仅提出停止决策；真正的物理急停仍必须由已有机器人安全控制器执行。

规划器在给定节点预算内穷举当前可执行波的分配，支持最多 8 个机器人、16 个子目标、每机器人每波一个目标。超过搜索上限会保留安全的当前方案并标记 `exact_wave_search=false`。它不求解整个任务时域的最优策略，也不支持将一个子目标直接分配给多个机器人做紧耦合搬运。可选依赖链的跨波价值仍由局部启发式处理，可能损失未来收益。

## 输入、回放与接口

- [mission.example.json](../experiments/mission.example.json) 是人工编写的合成任务定义，包含能力先验、目标价值、依赖、期限与预算。
- [replay.example.json](../experiments/replay.example.json) 演示缺失观测、机器人不可用、紧急事件和恢复。
- 所有事件有唯一 `id` 和单调时间；重复相同消息不重复更新，复用同一 ID 却改变内容会被拒绝。反馈只能结算当前活动目标。没有把 LLM 自报置信度或上游自然语言能力说明自动转换成真实概率。

ROS 构建后可运行：

```bash
ros2 launch riskweave_console riskweave_replanning.launch.py mission_file:=/absolute/path/mission.json policy:=selective
```

输入话题是 `/riskweave/replanning/events`（`std_msgs/String` 中的结构化 JSON）；输出是 `/riskweave/replanning/decision` 与 `/riskweave/replanning/proposed_tasks_json`。后者保留原 `robot_tasks`/`sequence` 形状，并附带子目标 ID 和 `preview_only=true`。它不向原机器人执行话题发命令，也不自动把自然语言目标转成结构化任务。

这样可以与原任务管理器并行观察，不会有两个规划器争夺执行权。接入真实执行还需要补齐任务中断确认、任务 ID 与机器人状态的映射、并发控制及协同动作验证；本轮未将预览接口冒充完整执行闭环。

## 对照实验如何解释

三种策略共享完全相同的规划器、风险约束、目标参数、能力更新和环境实现，仅比较触发与部分完成策略：

- `fixed`：固定周期调用；周期为示例预设值 2，没有声称在独立数据集上调优。
- `event`：相关事件或任务反馈触发。它是事件规则的结构化替代对照，**不是原论文的 LLM 基线复现**。
- `selective`：成本与风险门控，并可放弃代价不合算的可选工作。

实验包含稳定、干扰消息、能力退化、全队不可用和高规划代价五个合成条件。事件探测与执行结果来自明确编写的离散模型，没有 Gazebo 物理、VLM 感知或云 LLM。真实 API 调用数为 0，模型 token 和金额保持未知；规划费用是合成效用单位。

每个回合记录任务完成比例、完整完成、必需目标完成、按价值加权的完成比例、严重失败、重规划次数、规划效用费用、有效载荷字节和实际调度 CPU 墙钟时间。不能只用价值指标掩盖任务数量下降。

相同种子、任务和尝试使用相同随机源。原始 JSONL 和逐事件轨迹保存到新建输出目录；汇总包含源码和任务哈希。各条件使用跨种子统计，二元比例给 Wilson 区间；其他指标使用明确标注的正态近似。总体配对比较先在每个种子内平均固定条件，再在独立种子间构造区间，避免把同一种子的不同条件当成独立样本。

首轮 0–29 号种子用于发现“不可用时反复空规划”的工程缺陷，原输出保留。随后使用 1000–1049 号种子补充复测；修复事件 ID 冲突、过期反馈和必需任务排队时的重复求解判定后，又重复了该复测。这些结果在开发期间已查看，属于开发实验，不能当作最终未见测试集。后续研究仍需先冻结方法与参数，再使用新场景和新种子开展独立评价。

实际结果见 [RESEARCH_RESULTS.md](RESEARCH_RESULTS.md)。目前仅观察到规划费用与可选任务完成之间的取舍，未证明严重失败率改善，能力退化仍是明显短板。

## 原有提供商调用修复与计量

`requirements.txt` 改用与 `from google import genai` 匹配的 `google-genai`；Ollama 导入改为实际调用时加载；OpenAI 客户端延迟创建，避免选择其他后端时也要求 OpenAI 密钥；xAI 请求使用传入的模型名称；补上已存在 `listen.py` 的启动入口。

任务管理器的提供商调用记录到运行目录中的 `model_calls.jsonl`。记录请求模型、返回模型、SDK 方法是否被调用、时长、返回 usage 与有效载荷字节，不记录提示词、回复或密钥。初始化/导入失败与 SDK 调用分开记录。没有返回 usage 时保留空值，不把字符数换算成 token；金额不推测。OpenAI/xAI 的 SDK 自动重试设置为 0，其他 SDK 的实际网络尝试数未知。计量范围目前只覆盖集中任务管理器，不覆盖六个机器人节点内部的全部模型调用。

接口依据：[OpenAI 官方 Chat Completions 文档](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)、[Google Gen AI SDK](https://googleapis.github.io/python-genai/)、[Ollama Python](https://github.com/ollama/ollama-python)。未使用真实密钥逐个验证上游列出的模型，不能保证所有历史型号及参数当前可用。

## 仿真资源、环境与授权

缺失人物模型补为显式标注的程序化占位网格；家具照片和手机截图移除，材质改纯色；修复实际存在的纹理路径，清理无用的源网格与碰撞纹理依赖。几何和版权保留范围见 [RESOURCE_CHANGES.md](RESOURCE_CHANGES.md)。这些视觉变化不适合直接复用原论文的视觉任务评价结论。

[environment_probe.json](environment_probe.json) 记录实际环境探测。WSLg 的 EGL 小测试默认使用软件渲染器 `llvmpipe`；在单个进程显式设置 `GALLIUM_DRIVER=d3d12` 和 `MESA_D3D12_DEFAULT_ADAPTER_NAME=Intel` 后，实际识别为 Intel Iris Xe 的 D3D12 硬件后端。两次仅测离屏清屏与同步，不是完整场景帧率或 GPU 性能排名。Docker Hub 拉取最初发生 TLS 超时，后续改用 ECR Docker Library 镜像源及已解析的 amd64 摘要；容器构建/运行状态必须以实际记录为准。

已提供 `Dockerfile.research` 与 `tools/container_smoke.sh` 用于 ROS Humble 构建和实际消息通信检查。真实 Humble 容器中的发布/订阅已通过两个事件的检查，20 项研究检查也在 Python 3.10 中通过。完整构建和世界物理检查仍分别记录结果，不能由通信检查推断通过。容器测试不包含原有 GUI、收费模型与机器人执行闭环。源码只在运行时挂载，没有把凭据或项目历史复制进构建上下文。

主仓库授权仍未获上游明确声明：核验 GitHub 仓库字段为 `license=null`，许可证端点返回 404，见 [upstream_license_check.json](upstream_license_check.json)。保留现有声明，不以论文许可替代代码授权。

兼容转换：原始资源混用了新版 `gz-sim-*` 与 Fortress 标识。`tools/prepare_fortress_assets.py` 默认只列出改动；容器流程仅对隔离副本显式应用插件库、类命名空间及消息类型转换，并保存哈希。未在宿主源文件中悄悄改写版本；这也不是通用 SDF 版本迁移器。命名依据见 [Fortress 官方世界教程](https://gazebosim.org/docs/fortress/sdf_worlds/)。

真实 token/金额尚未自动回写结构化调度器。当前方法使用显式配置的规划效用费用，真实任务管理器的计量日志是后续校准接口，不能当成已经完成在线费用闭环。


## 本轮最终容器结果

13 个 ROS 包在隔离副本上全部构建成功；安装后的结构化决策节点通过两个真实 ROS 事件的发布/订阅检查；Ignition Gazebo 6.18.0 的 `food_court` 世界已初始化，统计消息观察到 327 个推进中的物理迭代。运行日志未发现错误行，有一条第三方 CoffeeTable 材质同时声明 `d`/`Tr` 的警告，未修改其透明度语义。

启动阶段保存的统计片段中，实时因子多在约 0.1–0.2；这不是稳态性能测试，也没有测 GUI 帧率。不能据此承诺完整三维系统实时或流畅运行。没有运行机器人任务执行、VLM 感知与云 LLM 的完整闭环。

构建中确认机器人描述包仅在 CMake/manifest 声明了 `urdf_tutorial`，没有实际引用；移除该无用教程依赖后完整构建通过。首次 shell 的 `set -u` 与 ROS 可选环境变量不兼容，也已修正，历史失败日志已随旧项目在项目外归档。

复用本机已构建镜像可运行：

```powershell
$taskRepo = (Get-Location).Path
$taskOut = Join-Path $taskRepo 'artifacts/ros'
New-Item -ItemType Directory -Force -Path $taskOut | Out-Null
docker run --rm -e ROS_LOCALHOST_ONLY=1 --mount "type=bind,source=$taskRepo,target=/work,readonly" --mount "type=bind,source=$taskOut,target=/output" riskweave-research:local bash /work/tools/container_smoke.sh
```

需要重建时，本机成功使用的底层镜像摘要为：

```bash
docker build -f Dockerfile.research --build-arg ROS_BASE_IMAGE=public.ecr.aws/docker/library/ros@sha256:a3f4de78e42cca693a543ece5798aedcf1cae0171fe71c334a047332cc72ef93 -t riskweave-research:local .
```

所有后台测试容器均按 `--rm` 退出，没有留下运行中的机器人/仿真进程。镜像保留在本地以便复现。


## 当前项目命名验证

当前名称以 `project.json` 为准。更名后重新运行的 750 个回合，其非耗时指标与归档基线逐项一致；算法核心文件的字节内容保持一致。26 项检查、5,000 条随机状态检查、新包名下 13 个 ROS 包构建、真实消息通信与世界物理启动均通过。细节见 [更名验证](rename_validation.json)。原实验记录没有被改写为本轮证据。
