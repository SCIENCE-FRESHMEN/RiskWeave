#!/usr/bin/env python3
"""Paired synthetic scheduling benchmark; no LLM, physics or paper reproduction."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'riskweave/riskweave_console'))
from riskweave_console.selective import Scheduler

REGIMES = ('stable', 'nuisance', 'capability_drift', 'unrecoverable', 'high_call_cost')


def uniform(seed, *keys):
    payload = json.dumps([seed, *keys], separators=(',', ':')).encode('utf-8')
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big') / 2 ** 64


def wire_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))


def run_episode(template, policy, regime, seed, trace_stream=None):
    mission = copy.deepcopy(template)
    if regime == 'high_call_cost':
        mission['config']['planning_cost'] = 2.0
        mission['config']['planning_budget'] = 8.0
    engine = Scheduler.from_dict(mission, policy)
    truth = {(r.id, skill): belief.mean for r in engine.robots.values() for skill, belief in r.skills.items()}
    duration = mission['metadata']['durations']
    running, attempt_counts = {}, {}
    feedback = {'completed': [], 'failed': []}
    observations = []
    harm = False
    byte_count = 0
    execution_loss = 0.0
    planner_seconds = 0.0
    horizon = mission['metadata']['horizon']
    for tick in range(horizon + 1):
        event = {'id': f'event_{tick}', 'time': tick,
                 'relevant': tick == 0 or any(g.release == tick for g in engine.goals.values())
                             or (regime == 'nuisance' and tick % 2 == 1),
                 **feedback, 'observations': observations}
        if regime == 'capability_drift' and tick >= 3:
            truth['delivery_bot', 'carry'] = 0.15
            if tick in (3, 5, 7):
                event['relevant'] = True
                event['observations'].append({'robot': 'delivery_bot', 'skill': 'carry',
                                              'success': uniform(seed, 'probe', tick) < 0.15})
        if regime == 'unrecoverable' and tick == 3:
            event['availability'] = {r: False for r in engine.robots}
            event['relevant'] = True
        started = time.perf_counter()
        decision = engine.step(event)
        planner_seconds += time.perf_counter() - started
        preview = engine.proposed_robot_tasks()
        byte_count += wire_bytes(event) + wire_bytes(decision) + wire_bytes(preview)
        if trace_stream:
            trace_stream.write(json.dumps({'regime': regime, 'seed': seed, 'policy': policy,
                                           'event': event, 'decision': decision}, sort_keys=True) + '\n')
        feedback = {'completed': [], 'failed': []}
        observations = []
        if tick == horizon:
            break
        # Removed/preempted tasks lose progress. Common random draws are keyed
        # by mission seed, goal, robot and attempt, never by policy loop order.
        for robot in list(running):
            if engine.active.get(robot) != running[robot]['goal']:
                del running[robot]
        for robot, goal_id in engine.active.items():
            if robot not in running:
                attempt_counts[robot, goal_id] = attempt_counts.get((robot, goal_id), 0) + 1
                running[robot] = {'goal': goal_id, 'remaining': duration[goal_id],
                                  'attempt': attempt_counts[robot, goal_id]}
                execution_loss += engine.goals[goal_id].execution_cost
        for robot, task in list(running.items()):
            task['remaining'] -= 1
            if task['remaining'] > 0:
                continue
            goal = engine.goals[task['goal']]
            success = uniform(seed, goal.id, robot, task['attempt'], 'outcome') < truth[robot, goal.skill]
            feedback['completed' if success else 'failed'].append(goal.id)
            observations.append({'robot': robot, 'skill': goal.skill, 'success': success})
            if not success:
                execution_loss += goal.failure_loss
                harm |= uniform(seed, goal.id, robot, task['attempt'], 'harm') < goal.harm_probability
            del running[robot]
    completed = {g for g, status in engine.status.items() if status == 'completed'}
    total_value = sum(g.value for g in engine.goals.values())
    completed_value = sum(engine.goals[g].value for g in completed)
    return {'policy': policy, 'regime': regime, 'seed': seed,
            'full_completion': int(len(completed) == len(engine.goals)),
            'required_completion': int(engine.protected <= completed),
            'task_completion_rate': len(completed) / len(engine.goals),
            'value_completion_rate': completed_value / total_value if total_value else 1.0,
            'severe_failure_episode': int(harm),
            'planning_calls': engine.planning_calls,
            'replanning_calls': max(0, engine.planning_calls - 1),
            'planning_cost_units': engine.spent,
            'net_realized_value_units': completed_value - engine.spent - execution_loss,
            'communication_utf8_bytes': byte_count,
            'scheduler_wall_seconds': planner_seconds,
            'model_sdk_calls': 0, 'model_tokens': None, 'model_monetary_cost': None,
            'final_status': engine.status}


def interval(values, binary=False):
    n = len(values)
    mean = statistics.fmean(values)
    if binary:
        z2 = 1.96 ** 2
        center = (mean + z2 / (2 * n)) / (1 + z2 / n)
        half = 1.96 * math.sqrt(mean * (1 - mean) / n + z2 / (4 * n * n)) / (1 + z2 / n)
        low, high = max(0, center - half), min(1, center + half)
    else:
        half = 1.96 * statistics.stdev(values) / math.sqrt(n) if n > 1 else 0
        low, high = mean - half, mean + half
    return {'n': n, 'mean': mean, 'ci95': [low, high],
            'interval': 'Wilson' if binary else 'normal approximation across seeds'}


def benchmark(template, episodes, output, seed_start=0):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    with (output / 'trace.jsonl').open('w', encoding='utf-8') as traces, (output / 'episodes.jsonl').open('w', encoding='utf-8') as raw:
        for regime in REGIMES:
            for seed in range(seed_start, seed_start + episodes):
                for policy in Scheduler.POLICIES:
                    row = run_episode(template, policy, regime, seed, traces)
                    rows.append(row)
                    raw.write(json.dumps(row, sort_keys=True) + '\n')
    binary = {'full_completion', 'required_completion', 'severe_failure_episode'}
    metrics = [*sorted(binary), 'task_completion_rate', 'value_completion_rate',
               'planning_calls', 'replanning_calls', 'planning_cost_units',
               'net_realized_value_units', 'communication_utf8_bytes', 'scheduler_wall_seconds']
    groups = {}
    for regime in REGIMES:
        groups[regime] = {}
        for policy in Scheduler.POLICIES:
            subset = [r for r in rows if r['policy'] == policy and r['regime'] == regime]
            groups[regime][policy] = {m: interval([r[m] for r in subset], m in binary) for m in metrics}
    comparisons = {}
    for baseline in ('fixed', 'event'):
        comparisons[baseline] = {}
        for metric in ['value_completion_rate', 'severe_failure_episode', 'planning_calls', 'net_realized_value_units']:
            deltas = []
            for seed in range(seed_start, seed_start + episodes):
                per_regime = []
                for regime in REGIMES:
                    pair = {r['policy']: r for r in rows if r['regime'] == regime and r['seed'] == seed}
                    per_regime.append(pair['selective'][metric] - pair[baseline][metric])
                deltas.append(statistics.fmean(per_regime))
            comparisons[baseline][metric] = interval(deltas)
    sources = [ROOT / 'riskweave/riskweave_console/riskweave_console/selective/core.py', Path(__file__)]
    return {'kind': 'synthetic_discrete_dispatch_benchmark', 'episodes': len(rows),
            'seeds_per_regime': episodes, 'regimes': list(REGIMES),
            'seed_start': seed_start, 'seed_end_inclusive': seed_start + episodes - 1,
            'paired_interval_unit': 'Independent seed, after averaging the fixed regimes within each seed',
            'mission_sha256': hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest(),
            'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'model_sdk_calls': 0, 'groups': groups, 'paired_selective_minus_baseline': comparisons,
            'limitations': [
                'Hand-authored synthetic parameters and discrete execution model; no physics, VLM, LLM or hardware.',
                'Event baseline is a trigger-rule surrogate with the same exact wave planner, not the original LLM planner.',
                'Scenario priors, rewards, durations, costs and fixed period were chosen for an engineering example, not tuned on a held-out dataset.',
                'Risk scores depend on supplied model assumptions and are not calibrated physical failure probabilities.',
                'Communication counts serialize events, decisions and previews; ROS/HTTP overhead is excluded.',
                'Planning cost uses synthetic utility units; no model prices or token usage are simulated.',
                'Intervals describe seeds in these fixed synthetic regimes, not generalization to other scenes.',
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mission', type=Path, default=ROOT / 'experiments/mission.example.json')
    parser.add_argument('--episodes', type=int, default=30)
    parser.add_argument('--seed-start', type=int, default=0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.episodes < 2:
        parser.error('Use at least two seeds to report an interval')
    template = json.loads(args.mission.read_text(encoding='utf-8'))
    summary = benchmark(template, args.episodes, args.output, args.seed_start)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'episodes': summary['episodes'], 'output': str(args.output),
                      'kind': summary['kind'], 'model_sdk_calls': 0}))


if __name__ == '__main__':
    main()
