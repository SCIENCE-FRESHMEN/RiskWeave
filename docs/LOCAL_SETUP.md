# 本地配置与运行数据

Windows 与 WSL 宿主没有安装 ROS 2。Docker 环境的实际构建和检查状态见 [环境记录](environment_probe.json)；原有 GUI、云模型和机器人完整执行闭环仍未复现。新研究原型可以直接在本机运行，见[研究扩展说明](RESEARCH_EXTENSION.md)。原有 README 中的模型可用性与安装耗时没有逐项验证。

## 运行历史位置

聊天管理器、任务管理器和六类机器人 LLM 节点现在默认使用：

```text
~/.riskweave/data/<package>/
```

例如聊天数据位于 `~/.riskweave/data/riskweave_console/`，机器人数据位于 `~/.riskweave/data/drone/` 等包专属目录。目录按需创建。机器人历史仍采用原有机器人名文件命名和启动清理行为；聊天管理器仍在启动时重置当前会话文件、在退出时追加会话记录。

本轮没有改变“是否自动恢复上一会话”的策略；原聊天管理器初始化中的自动 `load_history()` 调用仍为注释状态。上游 README 对自动恢复的描述不能当成本地已验证行为。

若要指定位置，在所有相关节点的启动终端设置同一个 `RISKWEAVE_DATA_DIR`，并使用源码目录之外的绝对路径：

```powershell
$env:RISKWEAVE_DATA_DIR = Join-Path $env:LOCALAPPDATA 'riskweave\runtime'
```

```bash
export RISKWEAVE_DATA_DIR="$HOME/.local/state/riskweave"
```

在不同终端或不同主机运行节点时，需要自行保证聊天管理器和任务管理器能够访问一致的当前会话数据。本轮没有新增跨主机日志同步，也没有解决多个并发会话共享同一目录的问题。

仓库中 21 个 `data/*.txt` 均为空占位文件，其中 17 个原有非空文件已清空。7 个 Python 包的安装配置不再收集 `data/*` 或 `data2/*`，避免把会话历史打入安装包。旧历史未自动迁移到新目录。

## 密钥配置

项目继续从进程环境读取 `OPENAI_API_KEY`、`GEMINI_API_KEY`、`XAI_API_KEY`。没有写入真实密钥，也没有修改提供商调用逻辑。

[`.env.example`](../.env.example) 仅列出变量名称；程序不会自动读取 `.env`。需要在启动节点的环境中自行设置变量。新增忽略规则覆盖本地 `.env`、历史文件和常见运行产物；忽略规则不会清除既有 Git 历史。

## 离线验证

使用 Python 3.10 或以上版本，在项目根目录运行：

```bash
python -B tools/verify_workspace.py
python -B tools/check_runtime_storage.py
```

第一个脚本进行语法、配置和部分资源引用检查，输出 JSON。第二个脚本在临时目录测试存储行为；聊天节点使用 ROS 通信桩，机器人部分只执行其实际的存储初始化语句。这些检查不需要模型调用，不代表 ROS 节点完整启动或仿真实验通过。
