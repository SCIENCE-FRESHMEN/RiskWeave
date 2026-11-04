#!/usr/bin/env python3
"""Exercise runtime storage without ROS, model calls or robot control.

The ChatManager uses ROS transport stubs. Robot initializers contribute only
their storage statements, so these checks do not claim full node startup.
"""
import ast
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class Logger:
    def __init__(self):
        self.errors = []

    def info(self, *args):
        pass

    def error(self, message):
        self.errors.append(message)


class NodeStub:
    def __init__(self, *args):
        self.logger = Logger()

    def get_logger(self):
        return self.logger

    def create_subscription(self, *args):
        return None

    def create_publisher(self, *args):
        return types.SimpleNamespace(publish=lambda msg: None)

    def create_service(self, *args):
        return None

    def destroy_node(self):
        pass


def load_chat_manager():
    names = ('rclpy', 'rclpy.node', 'std_msgs', 'std_msgs.msg', 'std_srvs', 'std_srvs.srv')
    modules = {name: types.ModuleType(name) for name in names}
    modules['rclpy.node'].Node = NodeStub
    modules['std_msgs.msg'].String = type('String', (), {})
    modules['std_srvs.srv'].Trigger = type('Trigger', (), {})
    spec = importlib.util.spec_from_file_location(
        'storage_check_chat_manager', ROOT / 'riskweave/riskweave_console/riskweave_console/chat_manager.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.ChatManager


def storage_statements(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    initializer = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    start = next(i for i, n in enumerate(initializer.body)
                 if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'data_root' for t in n.targets))
    # Evaluate the actual storage block through both history path assignments.
    end = next(i for i in range(start, len(initializer.body))
               if isinstance(initializer.body[i], ast.Assign)
               and any(isinstance(t, ast.Attribute) and t.attr == 'robot_task_history'
                       for t in initializer.body[i].targets))
    return compile(ast.Module(body=initializer.body[start:end + 1], type_ignores=[]),
                   str(path), 'exec')


class StorageChecks(unittest.TestCase):
    def test_chat_manager_writes_and_restores_from_external_directory(self):
        manager_class = load_chat_manager()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'RISKWEAVE_DATA_DIR': temp}):
            node = manager_class()
            self.assertEqual(Path(node.file_path_current).parent, Path(temp) / 'riskweave_console')
            self.assertTrue(Path(node.file_path_current).is_file())
            node.chat_entry = 'synthetic storage smoke check'
            node.chat_log = [node.chat_entry]
            node.save_history_current()
            node.destroy_node()
            self.assertEqual(node.logger.errors, [])
            restored = manager_class()
            restored.load_history()
            self.assertIn(node.chat_entry, restored.chat_log)
            self.assertNotIn(node.chat_entry, Path(restored.file_path_current).read_text())
            self.assertEqual(restored.logger.errors, [])

    def test_unset_empty_and_tilde_storage_roots(self):
        manager_class = load_chat_manager()
        with tempfile.TemporaryDirectory() as temp:
            for override in (None, '', '~/separate-data'):
                with self.subTest(override=override), patch.dict(os.environ), patch('os.path.expanduser') as expand:
                    # Keep the actual default/tilde expansion inside the temporary directory.
                    expand.side_effect = lambda value: str(Path(temp) / str(value).replace('\\', '/').removeprefix('~/'))
                    if override is None:
                        os.environ.pop('RISKWEAVE_DATA_DIR', None)
                    else:
                        os.environ['RISKWEAVE_DATA_DIR'] = override
                    node = manager_class()
                    suffix = 'separate-data/riskweave_console' if override else '.riskweave/data/riskweave_console'
                    self.assertEqual(Path(node.file_path).parent, Path(temp) / suffix)
                    self.assertEqual(node.logger.errors, [])

    def test_six_robot_packages_keep_histories_separate(self):
        nodes = [p for p in ROOT.rglob('*_llm.py')
                 if p.name != 'task_manager.py' and 'data_root =' in p.read_text(encoding='utf-8')]
        self.assertEqual(len(nodes), 6)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'RISKWEAVE_DATA_DIR': temp}):
            history_paths = []
            for path in nodes:
                with self.subTest(node=path.name):
                    node = types.SimpleNamespace(robot_name='robot1')
                    package_name = path.parent.name
                    exec(storage_statements(path), {'os': os, 'self': node, 'PACKAGE_NAME': package_name})
                    self.assertEqual(Path(node.history_file).parent, Path(temp) / package_name)
                    Path(node.history_file).write_text('synthetic ' + package_name)
                    self.assertEqual(Path(node.history_file).read_text(), 'synthetic ' + package_name)
                    self.assertEqual(Path(node.robot_task_history).parent, Path(temp) / package_name)
                    history_paths.append(node.history_file)
            self.assertEqual(len(set(history_paths)), 6)

    def test_task_manager_can_load_missing_history(self):
        path = ROOT / 'riskweave/riskweave_console/riskweave_console/task_manager.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        initializer = next(n for n in ast.walk(tree)
                           if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        empty_history = [n for n in initializer.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Attribute) and t.attr == 'chat_log' for t in n.targets)]
        load = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'load_history')
        namespace = {'os': os}
        exec(compile(ast.Module(body=[load], type_ignores=[]), str(path), 'exec'), namespace)
        with tempfile.TemporaryDirectory() as temp:
            node = types.SimpleNamespace(history_current=str(Path(temp) / 'missing.txt'))
            exec(compile(ast.Module(body=empty_history, type_ignores=[]), str(path), 'exec'), {'self': node})
            namespace['load_history'](node)
            self.assertEqual(node.chat_log, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
