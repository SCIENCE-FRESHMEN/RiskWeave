# RiskWeave ROS 工作区

本目录包含 `riskweave_console`、机器人接口、机器人 LLM 节点和仿真描述包。研究核心位于 `riskweave_console/riskweave_console/selective/`。

结构化决策启动入口：

```bash
ros2 launch riskweave_console riskweave_replanning.launch.py mission_file:=/absolute/path/mission.json
```

完整构建和世界检查采用根目录提供的 Humble/Fortress 容器流程；兼容转换仅作用于隔离副本。具体步骤见[运行说明](../docs/RESEARCH_EXTENSION.md)，来源见[来源记录](../docs/ORIGIN.md)。
