#!/usr/bin/env python3
"""Replay explicitly structured events without ROS or model credentials."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'riskweave/riskweave_console'))
from riskweave_console.selective import Scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mission', type=Path, default=ROOT / 'experiments/mission.example.json')
    parser.add_argument('--events', type=Path, default=ROOT / 'experiments/replay.example.json')
    parser.add_argument('--policy', choices=Scheduler.POLICIES, default='selective')
    args = parser.parse_args()
    mission = json.loads(args.mission.read_text(encoding='utf-8'))
    scheduler = Scheduler.from_dict(mission, args.policy)
    for event in json.loads(args.events.read_text(encoding='utf-8')):
        print(json.dumps(scheduler.step(event), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
