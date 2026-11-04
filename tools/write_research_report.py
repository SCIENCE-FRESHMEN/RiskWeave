#!/usr/bin/env python3
"""Generate a candid report from an existing, completed synthetic run."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def write_report(run):
    summary = json.loads((run/'summary.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (run/'episodes.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows) != summary['episodes']:
        raise ValueError('Episode count does not match summary')
    for relative, expected in summary['source_sha256'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Source has changed since the experiment: '+relative)
    metrics = ['task_completion_rate', 'required_completion', 'value_completion_rate',
               'severe_failure_episode', 'planning_calls', 'replanning_calls',
               'planning_cost_units', 'communication_utf8_bytes', 'scheduler_wall_seconds']
    aggregate = {p: {m: statistics.fmean(row[m] for row in rows if row['policy']==p) for m in metrics}
                 for p in ('fixed','event','selective')}
    summary['aggregate_fixed_regimes'] = aggregate
    summary['date'] = '2026-10-29'
    summary['raw_artifacts'] = {p.name: {'relative_path':p.relative_to(ROOT).as_posix(),
                                       'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size}
                                for p in [run/'episodes.jsonl', run/'trace.jsonl']}
    docs = ROOT/'docs'
    (docs/'RESEARCH_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    labels = {'fixed':'固定周期', 'event':'事件规则替代对照', 'selective':'选择性策略'}
    lines = ['# RiskWeave · 合成实验结果', '',
             f"运行日期：2026-10-29。{len(rows)} 个回合，5 个固定合成条件，每条件 {summary['seeds_per_regime']} 个种子（{summary['seed_start']}–{summary['seed_end_inclusive']}），每种子比较三种策略。所有数值从原始 JSONL 自动汇总。", '',
             '**这些是合成离散调度实验，不是 Gazebo、真实机器人、云 LLM 或原论文复现。**', '',
             '## 固定条件的等权平均', '',
             '| 策略 | 子目标完成比例 | 必需目标全部完成 | 按价值完成比例 | 严重失败回合 | 规划调用/回合 | 重规划/回合 | 规划效用费用/回合 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for policy, values in aggregate.items():
        lines.append(f"| {labels[policy]} | {values['task_completion_rate']:.2%} | {values['required_completion']:.2%} | {values['value_completion_rate']:.2%} | {values['severe_failure_episode']:.2%} | {values['planning_calls']:.3f} | {values['replanning_calls']:.3f} | {values['planning_cost_units']:.3f} |")
    a,b = aggregate['event'],aggregate['selective']
    lines += ['', f"相对事件规则替代对照，选择性策略的规划调用平均减少 {1-b['planning_calls']/a['planning_calls']:.2%}；子目标完成比例下降 {(a['task_completion_rate']-b['task_completion_rate'])*100:.2f} 个百分点，按价值完成比例下降 {(a['value_completion_rate']-b['value_completion_rate'])*100:.3f} 个百分点。必需目标完成比例和严重失败比例在本次样本中相同。这个结果呈现了费用与可选目标之间的取舍，不能表述为所有指标都提升。", '',
              '## 分条件结果', '',
              '| 条件 | 策略 | 必需目标全部完成 | 严重失败回合 | 平均规划调用 |',
              '| --- | --- | ---: | ---: | ---: |']
    for regime, policies in summary['groups'].items():
        for policy, values in policies.items():
            lines.append(f"| {regime} | {labels[policy]} | {values['required_completion']['mean']:.2%} | {values['severe_failure_episode']['mean']:.2%} | {values['planning_calls']['mean']:.3f} |")
    drift = summary['groups']['capability_drift']['selective']
    lines += ['', f"能力退化条件下，选择性策略的必需目标全部完成比例仅为 {drift['required_completion']['mean']:.2%}，严重失败回合比例为 {drift['severe_failure_episode']['mean']:.2%}，是明确的局限。当前稀疏观测与折扣能力估计没有在这些条件下显示出风险改善。不能将“风险预算代码存在”写成“已经实现真实安全保证”。", '',
              '## 统计与复现边界', '',
              '- 二元比例提供 Wilson 95% 区间；其他指标采用跨种子的正态近似，详细区间在 JSON 中。',
              '- 总体配对区间先在每个种子内平均五个固定条件，独立单位是种子，不是所有条件行。相同的观测差异不意味着真实风险差异已被排除。',
              '- `event` 对照使用同一结构化规划器，只替代事件触发规则；没有运行原论文的完整 LLM 基线。',
              '- 模型 SDK 调用为 0；token 与金额未测量。效用费用来自示例参数，不是货币。通信统计仅含事件、决策和预览的序列化有效载荷。',
              '- 首轮测试暴露过空规划缺陷，旧输出保留；当前不是预注册、独立场景泛化或发表级验证。', '',
              '[详细汇总与源码/任务哈希](RESEARCH_RESULTS.json) · [方法与运行说明](RESEARCH_EXTENSION.md)', '',
              f"原始记录：`{(run/'episodes.jsonl').relative_to(ROOT).as_posix()}`；逐事件轨迹：`{(run/'trace.jsonl').relative_to(ROOT).as_posix()}`。输出属于本地实验产物，默认被 Git 忽略，可从同一任务文件和种子重新生成。", '']
    (docs/'RESEARCH_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'episodes':len(rows),'report':'docs/RESEARCH_RESULTS.md','aggregate':aggregate}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    write_report(parser.parse_args().run.resolve())
