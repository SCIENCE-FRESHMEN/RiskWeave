#!/usr/bin/env python3
"""Offline invariants, provider contract and benchmark reproducibility checks."""
import ast
import copy
import itertools
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'riskweave/riskweave_console'))
sys.path.insert(0, str(ROOT / 'tools'))
from riskweave_console.selective import Belief, Goal, Robot, Config, Scheduler
from riskweave_console.model_meter import ModelMeter, token_usage
from run_selective_benchmark import run_episode


def fixture(config=None, goals=None, robots=None, policy='selective'):
    return Scheduler(robots or [Robot('robot', {'move': Belief(99, 1)})],
                     goals or [Goal('deliver', 'move', 10, required=True, harm_probability=0.1)],
                     config or Config(), policy)


class CoreChecks(unittest.TestCase):
    def test_uncertainty_and_evidence(self):
        prior = Belief(9, 1)
        bound = prior.failure_bound(0.1)
        prior.observe(False, 0.8)
        self.assertLess(prior.mean, 0.9)
        self.assertGreater(prior.failure_bound(0.1), bound)
        self.assertGreaterEqual(prior.failure_bound(0.01), prior.failure_bound(0.1))
        with self.assertRaises(ValueError):
            prior.observe('confident', 0.8)

    def test_optional_abandonment_and_required_prerequisite_protection(self):
        goals = [Goal('optional', 'move', 1, execution_cost=10),
                 Goal('prerequisite', 'move', 1, execution_cost=10),
                 Goal('required', 'move', 20, required=True, dependencies=['prerequisite'])]
        engine = fixture(goals=goals)
        result = engine.step({'id': 'start', 'time': 0})
        self.assertEqual(result['assignments'], {'robot': 'prerequisite'})
        self.assertEqual(result['status']['optional'], 'abandoned')
        self.assertEqual(result['status']['required'], 'pending')
        next_wave = engine.step({'id': 'feedback', 'time': 1, 'completed': ['prerequisite']})
        self.assertEqual(next_wave['assignments'], {'robot': 'required'})

    def test_emergency_ignores_planning_budget_and_stays_latched(self):
        engine = fixture()
        engine.step({'id': 'start', 'time': 0})
        engine.config.planning_budget = 0
        stopped = engine.step({'id': 'emergency', 'time': 1, 'emergency': True})
        self.assertEqual(stopped['action'], 'stop')
        self.assertEqual(stopped['assignments'], {})
        self.assertEqual(stopped['planning_calls'], 1)
        self.assertEqual(engine.step({'id': 'later', 'time': 2})['action'], 'stop')
        self.assertEqual(engine.step({'id': 'resume', 'time': 3, 'resume': True})['assignments'], {})

    def test_risk_budget_includes_preempted_attempts(self):
        goals = [Goal(f'goal_{i}', 'move', 10 ** i, release=i, harm_probability=0.1)
                 for i in range(7)]
        engine = fixture(config=Config(risk_budget=0.012, planning_budget=100), goals=goals)
        for tick in range(7):
            result = engine.step({'id': f'event_{tick}', 'time': tick, 'relevant': True})
            self.assertLessEqual(result['risk_reserved'] + (result['active_risk_score'] or 0),
                                 engine.config.risk_budget + 1e-12)
        self.assertGreater(engine.risk_reserved, 0)

    def test_duplicate_and_invalid_event_do_not_double_update(self):
        engine = fixture()
        event = {'id': 'start', 'time': 0,
                 'observations': [{'robot': 'robot', 'skill': 'move', 'success': False}]}
        engine.step(event)
        alpha, beta = engine.robots['robot'].skills['move'].alpha, engine.robots['robot'].skills['move'].beta
        self.assertEqual(engine.step(event)['action'], 'duplicate')
        with self.assertRaises(ValueError):
            engine.step({**event, 'time': 1})
        self.assertEqual((alpha, beta), (engine.robots['robot'].skills['move'].alpha,
                                        engine.robots['robot'].skills['move'].beta))
        before = copy.deepcopy(engine.status)
        with self.assertRaises(ValueError):
            engine.step({'id': 'bad', 'time': 1, 'completed': ['deliver'],
                         'availability': {'unknown': False}})
        self.assertEqual(before, engine.status)
        self.assertNotIn('bad', engine.seen_events)

    def test_missing_observations_are_not_fabricated(self):
        engine = fixture()
        engine.step({'id': 'start', 'time': 0})
        for i in range(1, 5):
            engine.step({'id': f'event_{i}', 'time': i, 'relevant': True})
        self.assertEqual(engine.robots['robot'].skills['move'].alpha, 99)
        self.assertEqual(engine.robots['robot'].skills['move'].beta, 1)
        self.assertEqual(engine.planning_calls, 1)

    def test_fixed_period_and_event_rule(self):
        for policy, expected in [('fixed', 2), ('event', 3), ('selective', 1)]:
            engine = fixture(policy=policy)
            for tick in range(3):
                engine.step({'id': f'event_{tick}', 'time': tick, 'relevant': True})
            self.assertEqual(engine.planning_calls, expected)

    def test_waiting_required_work_does_not_replan_a_fully_occupied_required_wave(self):
        engine = fixture(goals=[Goal('first', 'move', 20, required=True),
                                Goal('second', 'move', 0.1, required=True)])
        engine.step({'id': 'start', 'time': 0})
        # The relaxed value bound also accounts for waiting work; the lower
        # value goal is too small to justify another optimizer invocation.
        engine.step({'id': 'nuisance', 'time': 1, 'relevant': True})
        self.assertEqual(engine.planning_calls, 1)

    def test_new_required_goal_preempts_optional_work(self):
        engine = fixture(goals=[Goal('optional', 'move', 30),
                                Goal('required', 'move', 1, required=True, release=1)])
        engine.step({'id': 'start', 'time': 0})
        result = engine.step({'id': 'new_request', 'time': 1})
        self.assertEqual(result['assignments'], {'robot': 'required'})

    def test_search_limit_retains_safe_incumbent(self):
        engine = fixture(config=Config(max_search_nodes=1))
        decision = engine.step({'id': 'start', 'time': 0})
        self.assertFalse(decision['exact_wave_search'])
        self.assertEqual(decision['assignments'], {})
        self.assertEqual(engine.planning_calls, 1)

    def test_unavailable_team_does_not_repeat_empty_optimization(self):
        engine = fixture()
        engine.step({'id': 'start', 'time': 0})
        for tick in range(1, 6):
            decision = engine.step({'id': f'event_{tick}', 'time': tick,
                                    'availability': {'robot': False}, 'relevant': True})
            self.assertEqual(decision['assignments'], {})
        self.assertEqual(engine.planning_calls, 1)
        restored = engine.step({'id': 'restored', 'time': 6, 'availability': {'robot': True}})
        self.assertEqual(restored['assignments'], {'robot': 'deliver'})

    def test_optional_only_work_below_call_cost_is_abandoned_without_search(self):
        engine = fixture(goals=[Goal('small', 'move', 0.2)])
        result = engine.step({'id': 'start', 'time': 0})
        self.assertEqual(result['action'], 'abandon')
        self.assertEqual(result['status']['small'], 'abandoned')
        self.assertEqual(result['planning_calls'], 0)

    def test_dependency_validation_and_nan(self):
        with self.assertRaises(ValueError):
            fixture(goals=[Goal('a', 'move', 1, dependencies=['b']),
                           Goal('b', 'move', 1, dependencies=['a'])])
        for value in (float('nan'), float('inf'), -1):
            with self.assertRaises(ValueError):
                Config(planning_budget=value)
        with self.assertRaises(ValueError):
            fixture().step({'id': 'bad', 'time': 0, 'relevant': 'yes'})

    def test_late_completion_does_not_satisfy_a_deadline(self):
        engine = fixture(goals=[Goal('deliver', 'move', 10, required=True, deadline=1)])
        engine.step({'id': 'start', 'time': 0})
        decision = engine.step({'id': 'late', 'time': 2, 'completed': ['deliver']})
        self.assertEqual(decision['status']['deliver'], 'expired')

    def test_wave_solution_matches_independent_bruteforce(self):
        rng = random.Random(4107)
        for trial in range(30):
            robots = [Robot(f'r{i}', {'move': Belief(rng.randint(2, 20), rng.randint(1, 8))}) for i in range(2)]
            goals = [Goal(f'g{i}', 'move', rng.randint(1, 10), required=i == 0,
                          harm_probability=rng.choice([0, 0.1, 0.5])) for i in range(3)]
            engine = fixture(config=Config(risk_budget=0.15), goals=goals, robots=robots)
            assignment, _ = engine._plan(0)
            score = engine._score(assignment)
            best = (0, 0.0, 0)
            # Independently enumerate each robot's choice, including idling.
            for choices in itertools.product([None, *[g.id for g in goals]], repeat=2):
                chosen = [g for g in choices if g is not None]
                if len(set(chosen)) != len(chosen):
                    continue
                reward = risk = count = 0
                for robot, goal_id in zip(robots, choices):
                    if goal_id is None:
                        continue
                    goal = engine.goals[goal_id]
                    belief = robot.skills['move']
                    reward += goal.value * belief.mean
                    risk += goal.harm_probability * belief.failure_bound(0.1)
                    count += int(goal.required)
                if risk <= 0.15 + 1e-12:
                    best = max(best, (count, reward, -len(chosen)))
            self.assertEqual((score[0], score[1], -len(assignment)), best, trial)


class MeterChecks(unittest.TestCase):
    def test_usage_is_reported_not_estimated_from_text(self):
        response = types.SimpleNamespace(usage=types.SimpleNamespace(prompt_tokens=17, completion_tokens=9, total_tokens=26))
        self.assertEqual(token_usage(response, 'openai'), {'input_tokens': 17, 'output_tokens': 9, 'total_tokens': 26})
        self.assertIsNone(token_usage(None, 'openai')['input_tokens'])
        self.assertEqual(token_usage({'usage_metadata': {'prompt_token_count': 7, 'candidates_token_count': 3}}, 'gemini')['input_tokens'], 7)

    def test_metadata_omits_sensitive_content_and_records_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'meter.jsonl'
            meter = ModelMeter(path)
            with meter.call('openai', 'requested', [{'role': 'user', 'content': 'private_test_payload'}]) as call:
                call.response = types.SimpleNamespace(model='returned', usage=None)
            with self.assertRaises(RuntimeError):
                with meter.call('openai', 'requested', []):
                    raise RuntimeError('private_exception_payload')
            text = path.read_text(encoding='utf-8')
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertNotIn('private_test_payload', text)
            self.assertNotIn('private_exception_payload', text)
            self.assertEqual(rows[0]['returned_model'], 'returned')
            self.assertIsNone(rows[0]['input_tokens'])
            self.assertEqual(rows[1]['error_type'], 'RuntimeError')

    def test_xai_forwards_selected_model(self):
        tree = ast.parse((ROOT / 'riskweave/riskweave_console/riskweave_console/task_manager.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'call_xai')
        captured = {}
        class Client:
            def __init__(self, **kwargs):
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def create(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(model=kwargs['model'], choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='ok'))])
        namespace = {'OpenAI': Client, 'xai_api_key': 'synthetic_unused_value'}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<provider_contract>', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as temp:
            node = types.SimpleNamespace(model_meter=ModelMeter(Path(temp) / 'calls.jsonl'))
            self.assertEqual(namespace['call_xai'](node, [], model_='requested-model'), 'ok')
            self.assertEqual(captured['model'], 'requested-model')


class ReplayChecks(unittest.TestCase):
    def test_paired_environment_is_reproducible(self):
        mission = json.loads((ROOT / 'experiments/mission.example.json').read_text(encoding='utf-8'))
        first = run_episode(mission, 'selective', 'capability_drift', 7)
        second = run_episode(mission, 'selective', 'capability_drift', 7)
        first.pop('scheduler_wall_seconds')
        second.pop('scheduler_wall_seconds')
        self.assertEqual(first, second)
        self.assertEqual(first['model_sdk_calls'], 0)

    def test_ros_adapter_contract_with_transport_stubs(self):
        class FakeNode:
            def __init__(self, *args):
                self.params = {}
                self.published = {}
            def declare_parameter(self, name, default):
                self.params[name] = str(ROOT/'experiments/mission.example.json') if name == 'mission_file' else default
            def get_parameter(self, name):
                return types.SimpleNamespace(value=self.params[name])
            def create_publisher(self, kind, topic, depth):
                self.published[topic] = []
                return types.SimpleNamespace(publish=lambda msg: self.published[topic].append(msg.data))
            def create_subscription(self, *args):
                return object()
            def get_logger(self):
                return types.SimpleNamespace(info=lambda msg: None, error=lambda msg: None)
        modules = {name: types.ModuleType(name) for name in ['rclpy', 'rclpy.node', 'std_msgs', 'std_msgs.msg']}
        modules['rclpy.node'].Node = FakeNode
        modules['std_msgs.msg'].String = type('String', (), {})
        spec = importlib.util.spec_from_file_location('riskweave_console.riskweave_replanner', ROOT/'riskweave/riskweave_console/riskweave_console/riskweave_replanner.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
            node = module.RiskWeaveReplanner()
            node.on_event(types.SimpleNamespace(data='{"id":"start","time":0}'))
            decision = json.loads(node.published['/riskweave/replanning/decision'][-1])
            self.assertEqual(decision['action'], 'replan')
            self.assertTrue(json.loads(node.published['/riskweave/replanning/proposed_tasks_json'][-1])['preview_only'])
            node.on_event(types.SimpleNamespace(data='{'))
            self.assertEqual(len(node.published['/riskweave/replanning/decision']), 1)
            self.assertNotIn('/task_manager/tasks_json', node.published)


if __name__ == '__main__':
    unittest.main(verbosity=2)
