# RiskWeave：来源、作者与许可证现状

RiskWeave 基于上游 CoMuRoS，本地修改涉及去标识化、运行历史存储隔离、提供商调用修复及新增的选择性调度研究原型。原有任务分配、事件相关性规则、任务重规划及机器人执行框架属于上游已有工作。当前工作区不宣称独立原创这些功能。

## 可核验来源

- [正式论文](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2026.1843313/full)：Suraj Borate、Bhavish Rai B、Vipul Pardeshi、Madhu Vadali，2026。*CoMuRoS - An LLM-based generalizable hierarchical task planning and execution framework for heterogeneous robot teams with event-driven re-planning*. Frontiers in Robotics and AI，13:1843313。出版页面显示日期为 2026-08-04。
- [上游项目网站](https://comuros.github.io/)：提供项目介绍，并链接到 [上游源码仓库](https://github.com/CoMuRoS/CoMuRoS)。本地目录没有 `.git`，因此不能确认下载版本对应的提交，也未将其当作论文发布版的完整副本。
- [负责人官方资料](https://iitgn.ac.in/hi/faculty/me/fac-madhu)：核验时列示 Madhu Vadali 为机械工程副教授（Associate Professor）。该身份仅作为来源核验记录，不代表本地开发者的机构归属。

以上网页于 2026-10-29 核验。上游网站中的预印本引用与正式论文版本不同；本文件优先引用正式期刊条目。

## 署名与联系方式的处理

9 个相关 ROS 包的原维护者姓名转为 `author` 字段；7 个 Python 包的原姓名转为 `author` 字段。个人维护者邮箱移除，当前维护者字段显式标记为未配置的本地开发联系人，使用不可投递的 `example.invalid` 占位域。

原作者、论文引用、第三方致谢和现有版权声明均保留。第三方机器人模型、材质、测试模板中的公开作者及其联系元数据未批量修改。公开作者署名不是本地运行所需的个人配置，也不能通过去标识化变成本地原创贡献。

## 许可证检查

当前目录没有根 `LICENSE`。多个主包的 `package.xml` 和 `setup.py` 仍含上游遗留的 `TODO: License declaration`；本轮没有虚构或补填许可证。

`yahboom_rosmaster_description/LICENSE`、`yahboom_rosmaster_gazebo/LICENSE`、测试模板的版权头，以及部分模型内的版权/许可文字原样保留。论文的开放获取许可不能自动解释为整个源码工作区的授权；需要发布或再分发时，应另行核清主代码与各资产的授权范围。

## 本轮新增内容

- 工作区维护信息去标识化与个人开发机路径清理。
- 8 个节点使用可配置的源码外运行历史目录，不再安装随包历史。
- 离线检查工具、运行存储隔离检查及本轮审计文档。

上述第一阶段内容是工程修改。后续新增的结构化调度原型、合成实验和 ROS 决策预览见 [研究扩展](RESEARCH_EXTENSION.md)；这些新增代码不等于已经证明学术新颖性、真实机器人安全性或原论文实验结果。


## 当前名称与来源名称的区别

当前本地派生项目名称为 **RiskWeave**（风险与成本约束的多机器人选择性重规划）；源码目录为 `riskweave`，控制台包为 `riskweave_console`。

上游项目原名 **CoMuRoS**、原控制台包名 `chatty` 仅作为来源与迁移事实保留在本文件。正式论文题名、原作者、上游网址及第三方版权不能改写为本地新项目的成果。

当前配置采用 `RISKWEAVE_DATA_DIR` 与 `RISKWEAVE_PYTHON`，默认数据位置为 `~/.riskweave/data/`。本轮未自动迁移或合并原有项目外运行历史。

更名前的完整项目、实验日志和审计记录已在项目外原样归档。当前报告使用新命名重新执行产生的证据；历史实测数值没有通过字符串替换伪装成新测试。
