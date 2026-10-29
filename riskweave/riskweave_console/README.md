# RiskWeave Console

ROS/Python 包名：`riskweave_console`。提供聊天 GUI、任务管理器以及 `riskweave_replanner` 结构化调度预览节点。

```bash
ros2 launch riskweave_console riskweave.launch.py config_file:=robot_config_default
ros2 launch riskweave_console riskweave_replanning.launch.py mission_file:=/absolute/path/mission.json policy:=selective
```

结构化输入：`/riskweave/replanning/events`。输出：`/riskweave/replanning/decision` 与 `/riskweave/replanning/proposed_tasks_json`。预览输出没有接入实际机器人执行话题。

运行数据默认保存到 `~/.riskweave/data/riskweave_console/`，使用 `RISKWEAVE_DATA_DIR` 可覆盖根目录。程序不自动加载 `.env`。模型密钥仍从相应提供商的标准环境变量读取。

查看[根目录使用说明](../../README.md)、[方法与验证边界](../../docs/RESEARCH_EXTENSION.md)和[来源记录](../../docs/ORIGIN.md)。
