# RiskWeave

RiskWeave is a research framework for risk- and cost-aware selective replanning of heterogeneous robot teams driven by LLM planners. It is derived from [CoMuRoS](https://github.com/CoMuRoS/CoMuRoS) (see [Origin and attribution](#origin-and-attribution)) with a new, independently runnable selective scheduling prototype on top of the original task allocation / event-driven replanning / robot execution stack.

Python 3.10+ · ROS 2 (Humble) for the full system · the research module itself needs only the standard library.

## What it does

The original CoMuRoS stack lets an LLM task manager allocate goals to a robot team and replan on task events. RiskWeave adds `selective/core.py`, a structured scheduler that, before replanning:

1. tracks per-robot skill success rates with Beta posteriors (discounted for capability drift);
2. computes a failure-risk score per assignment (Cantelli bound × configured consequence) under an explicit risk budget;
3. scores each candidate assignment by expected net value (`value·μ − failure_loss·(1−μ) − execution_cost`);
4. triggers replanning only when a relaxed value upper bound can still pay for the planning/communication/latency cost, and drops low-value optional work when it cannot — required goals are never dropped for low value;
5. reports partial completion honestly (completed / failed / expired / abandoned / unreachable).

Full method definition and boundaries: [docs/RESEARCH_EXTENSION.md](docs/RESEARCH_EXTENSION.md).

## Results

From a 750-episode synthetic experiment (5 fixed regimes × 50 seeds, seeds 1000–1049, 2026-10-29). All numbers below are taken verbatim from [`docs/RESEARCH_RESULTS.json`](docs/RESEARCH_RESULTS.json) (`aggregate_fixed_regimes`); narrative summary in [`docs/RESEARCH_RESULTS.md`](docs/RESEARCH_RESULTS.md).

Equal-weighted mean over the 5 fixed regimes:

| Policy | Subgoal completion | Value-weighted completion | Required goals complete | Severe-failure episodes | Planning calls / episode | Planning cost units / episode |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `fixed` (periodic) | 74.80% | 80.12% | 46.00% | 7.60% | 3.764 | 2.842 |
| `event` (rule trigger) | 74.80% | 80.12% | 46.00% | 7.60% | 3.764 | 2.842 |
| `selective` (RiskWeave) | 69.27% | 79.91% | 46.00% | 7.60% | 1.800 | 1.540 |

What this actually shows — and what it does not:

- The selective policy cuts planning calls by **52.2%** and planning cost by **45.8%** against the event-rule baseline, at a cost of **−5.53 pp** subgoal completion (mostly optional goals it deliberately drops) and −0.21 pp value-weighted completion. Required-goal completion and severe-failure rate are unchanged in this sample.
- **No safety improvement was demonstrated.** Severe-failure rate is identical across policies, and in the `capability_drift` regime the selective policy reaches only 2% required-goal completion — a known weakness of the current sparse-observation / discounted-capability estimate.
- These are synthetic discrete scheduling experiments: zero LLM API calls, no Gazebo physics, no real robots, no reproduction of the original paper's experiments. Planning "cost" is a synthetic utility unit, not money.
- Raw per-episode records (`artifacts/.../episodes.jsonl`, `trace.jsonl`) are local, git-ignored outputs; the JSON summary includes source/mission SHA-256 hashes so any rerun can be compared.

## Architecture (actual code layout)

```
RiskWeave
├── run_research.ps1 / run_research.sh   # one-command entry (verify / replay / benchmark)
├── project.json                         # naming, env vars, launch entrypoints
├── requirements.txt                     # deps for the GUI / LLM / speech stack
├── Dockerfile.research                  # ROS Humble build + smoke-test image
├── docs/
│   ├── RESEARCH_EXTENSION.md            # method definitions, boundaries, run instructions
│   ├── RESEARCH_RESULTS.md / .json      # experiment results (see above)
│   └── LOCAL_SETUP.md
├── experiments/
│   ├── mission.example.json             # hand-written synthetic mission definition
│   └── replay.example.json              # missing observations, robot loss, e-stop, recovery
├── tools/
│   ├── run_selective_benchmark.py       # the 750-episode experiment runner
│   ├── run_selective_replay.py          # replay a mission/replay JSON
│   ├── check_selective_replanning.py    # 20 research self-checks
│   ├── verify_workspace.py, check_*.py  # offline workspace / resource checks
│   └── container_ros_smoke.py, container_gazebo_smoke.py, container_smoke.sh
└── riskweave/
    ├── riskweave_console/               # ROS 2 console package
    │   ├── riskweave_console/
    │   │   ├── task_manager.py          # centralized LLM task manager (provider metering → model_calls.jsonl)
    │   │   ├── chat_gui.py, chat_manager.py, listen.py, speak.py, microphone.py
    │   │   ├── riskweave_replanner.py   # ROS decision-preview node (no direct actuator commands)
    │   │   └── selective/core.py        # the new risk/cost-gated selective scheduler
    │   ├── config/robot_config_*.json   # 58 scenario configurations
    │   └── launch/                      # riskweave.launch.py, riskweave_replanning.launch.py
    ├── robot_llms/                      # per-robot LLM nodes: cleaning_bot, delivery_bot, drone, robot_llm
    ├── robot_interface/                 # shared ROS interfaces
    └── robots/                          # third-party robot & Gazebo assets (x3_uav, yahboom rosmaster,
                                         #   multi_robot models/worlds); large meshes/textures, see note below
```

## One-command reproduction

Windows (PowerShell, repo root):

```powershell
$env:RISKWEAVE_PYTHON = "path\to\python.exe"   # optional; defaults to python on PATH
.\run_research.ps1 -Mode verify      # 6 offline check suites
.\run_research.ps1 -Mode replay      # deterministic replay of the example mission
.\run_research.ps1 -Mode benchmark -Episodes 50 -SeedStart 1000   # regenerate the experiment
```

Linux/macOS:

```bash
python3 -B tools/check_selective_replanning.py
python3 -B tools/run_selective_replay.py
python3 -B tools/run_selective_benchmark.py --episodes 50 --seed-start 1000 --output artifacts/new-run
```

The benchmark writes raw `episodes.jsonl` / `trace.jsonl` plus a summary (with source and mission hashes) into a new `artifacts/<run>` directory. It never calls paid APIs and never overwrites existing outputs.

### Full ROS/Gazebo system (optional, heavier)

```bash
pip install -r requirements.txt          # GUI + LLM providers + speech; needs ffmpeg/portaudio on Linux
docker build -f Dockerfile.research -t riskweave-research:local .
docker run --rm --mount "type=bind,src=$(pwd),dst=/work,readonly" riskweave-research:local bash /work/tools/container_smoke.sh
# after colcon build:
ros2 launch riskweave_console riskweave.launch.py
ros2 launch riskweave_console riskweave_replanning.launch.py mission_file:=/abs/path/mission.json policy:=selective
```

There is no benchmark data download step: the research experiments are fully self-contained, and the robot/simulation assets are in-tree under `riskweave/robots/`.

### Simulation assets note

`riskweave/robots/` (~410 MB) is the bulk of this repository. These third-party robot meshes, textures, models and worlds are referenced by the URDF/SDF/world files and the resource checks (`tools/check_simulation_resources.py`), so they are kept in-tree rather than turned into release attachments. If clone size matters, prefer a shallow clone or provide the assets as release attachments and strip this directory.

## Origin and attribution

RiskWeave is based on upstream **CoMuRoS**: *Suraj Borate, Bhavish Rai B, Vipul Pardeshi, Madhu Vadali, "CoMuRoS - An LLM-based generalizable hierarchical task planning and execution framework for heterogeneous robot teams with event-driven re-planning", Frontiers in Robotics and AI 13:1843313 (2026).* The original task allocation, event-correlation rules, task replanning and robot execution framework are upstream work, not claimed here. The upstream repository has no declared license; third-party model licenses inside `riskweave/robots/` are retained as-is. There is no root LICENSE file yet — do not redistribute before that is resolved.

## Citation

```bibtex
@misc{riskweave,
  title  = {RiskWeave: risk- and cost-aware selective replanning for heterogeneous robot teams},
  note   = {Built on CoMuRoS (Borate et al., Frontiers in Robotics and AI, 2026)},
  year   = {2026},
  url    = {https://github.com/SCIENCE-FRESHMEN/RiskWeave}
}
```
