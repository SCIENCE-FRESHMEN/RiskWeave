#!/usr/bin/env python3
"""Reproducible state-invariant fuzz check; not a physical safety proof."""
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'riskweave/riskweave_console'))
from riskweave_console.selective import Scheduler, Robot, Goal, Belief, Config


def check():
    rng = random.Random(793117)
    events = 0
    for trial in range(100):
        robots = [Robot(f'r{i}', {'move':Belief(rng.randint(2,20),rng.randint(1,5))}) for i in range(3)]
        goals = [Goal(f'g{i}','move',rng.uniform(0.1,20), required=i<2,
                      harm_probability=rng.uniform(0,0.3), release=i//2, deadline=30) for i in range(6)]
        scheduler = Scheduler(robots,goals,Config(risk_budget=0.5),policy=rng.choice(Scheduler.POLICIES))
        for tick in range(50):
            feedback = {'completed':[], 'failed':[]}
            for goal in list(scheduler.active.values()):
                if rng.random()<0.2:
                    feedback['completed' if rng.random()<0.8 else 'failed'].append(goal)
            observation = {'robot':f'r{rng.randrange(3)}','skill':'move','success':rng.random()<0.75}
            event = {'id':f'e{tick}','time':tick,'relevant':rng.random()<0.5,**feedback,
                     'observations':[observation],
                     'availability':{f'r{i}':rng.random()>0.2 for i in range(3)}}
            if rng.random()<0.02:
                event['emergency'] = True
            elif rng.random()<0.2:
                event['resume'] = True
            decision = scheduler.step(event)
            events += 1
            assert decision['risk_reserved']+(decision['active_risk_score'] or 0)<=scheduler.config.risk_budget+1e-10, (trial,tick)
            assert scheduler.spent<=scheduler.config.planning_budget+1e-10
            assert len(set(scheduler.active.values()))==len(scheduler.active)
            for robot, goal in scheduler.active.items():
                assert scheduler.robots[robot].available and scheduler.status[goal]=='pending'
                assert all(scheduler.status[d]=='completed' for d in scheduler.goals[goal].dependencies)
            assert not any(scheduler.status[g]=='abandoned' for g in scheduler.protected)
    return {'kind':'randomized_state_invariant_check','passed':True,'seed':793117,
            'missions':100,'events':events,'physical_safety_proof':False}


if __name__=='__main__':
    print(json.dumps(check()))
