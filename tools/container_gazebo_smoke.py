#!/usr/bin/env python3
"""Verify headless world physics advances; not a robot/vision experiment."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def decode(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')


def main():
    output = Path('/output')
    world = Path('/ws/install/multi_robot/share/multi_robot/worlds/food_court.sdf')
    if not world.exists():
        world = Path('/ws/install/share/multi_robot/worlds/food_court.sdf')
    assert world.is_file(), 'Installed world was not found'
    environment = os.environ.copy()
    environment['IGN_PARTITION'] = 'riskweave_smoke_' + str(os.getpid())
    resources = [Path('/ws/install/multi_robot/share/multi_robot/models'),
                 Path('/ws/install/yahboom_rosmaster_gazebo/share/yahboom_rosmaster_gazebo/models'),
                 Path('/ws/install/share/multi_robot/models'),
                 Path('/ws/install/share/yahboom_rosmaster_gazebo/models')]
    environment['IGN_GAZEBO_RESOURCE_PATH'] = ':'.join(str(p) for p in resources if p.exists())
    sample, topics = '', []
    with (output/'gazebo.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen(['ign','gazebo','-r','-s','-v','3',str(world)],
                                  stdout=log, stderr=subprocess.STDOUT, env=environment, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and server.poll() is None:
                query = subprocess.run(['ign','topic','-l'], capture_output=True, env=environment, timeout=5)
                topics = decode(query.stdout).splitlines()
                stats = next((t.strip() for t in topics if t.strip().endswith('/stats') and '/world/' in t), None)
                if stats:
                    try:
                        message = subprocess.run(['ign','topic','-e','-t',stats], capture_output=True,
                                                 env=environment, timeout=3)
                        sample = decode(message.stdout)
                    except subprocess.TimeoutExpired as exc:
                        sample = decode(exc.stdout)
                    if any(int(n)>0 for n in re.findall(r'iterations:\s*(\d+)',sample)):
                        break
                time.sleep(0.2)
            iterations = [int(n) for n in re.findall(r'iterations:\s*(\d+)',sample)]
            passed = bool(iterations and max(iterations)>0)
            report = {'kind':'headless_gazebo_world_physics_smoke','passed':passed,
                      'world':world.name,'max_observed_iterations':max(iterations,default=0),
                      'statistics_sample':sample[:1500],
                      'robot_execution_experiment':False,'gui_fps_measured':False,
                      'limitation':'World server progress only; no spawned robot control, VLM or selective replanning evaluation.'}
            (output/'gazebo_smoke.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({k:v for k,v in report.items() if k!='statistics_sample'}))
            assert passed, 'No advancing Gazebo physics statistics were observed; inspect gazebo.log'
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGINT)
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGTERM)
                    server.wait(timeout=5)


if __name__ == '__main__':
    main()
