"""Finite, single-robot-per-subgoal scheduling with a cheap replanning gate.

Risk scores are conditional on a Beta-Bernoulli capability model and supplied
harm probabilities. They are not certified physical safety probabilities.
The exact planner searches one dispatch wave, not an optimal mission horizon.
"""
from dataclasses import dataclass, field, asdict
import json
import math
import re
from typing import Optional


def finite(value, name, low=0.0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    if not math.isfinite(value) or value < low or (high is not None and value > high):
        raise ValueError(f'{name} outside allowed range')
    return float(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value):
        raise ValueError('Identifiers must use lowercase letters, digits and underscores')
    return value


@dataclass
class Belief:
    alpha: float = 9.0
    beta: float = 1.0

    def __post_init__(self):
        self.alpha = finite(self.alpha, 'alpha', 1e-9)
        self.beta = finite(self.beta, 'beta', 1e-9)

    @property
    def mean(self):
        return self.alpha / (self.alpha + self.beta)

    def failure_bound(self, delta):
        """One-sided Cantelli posterior bound, conditional on the stated model."""
        delta = finite(delta, 'posterior_tail_probability', 1e-9, 1 - 1e-9)
        total = self.alpha + self.beta
        variance = self.alpha * self.beta / (total * total * (total + 1))
        return min(1.0, 1 - self.mean + math.sqrt(variance * (1 - delta) / delta))

    def observe(self, success, decay):
        if type(success) is not bool:
            raise ValueError('Capability observations must be boolean, not model confidence')
        # Discount excess evidence toward a uniform prior for capability drift.
        self.alpha = 1 + decay * (self.alpha - 1) + int(success)
        self.beta = 1 + decay * (self.beta - 1) + int(not success)


@dataclass
class Robot:
    id: str
    skills: dict
    available: bool = True

    def __post_init__(self):
        identifier(self.id)
        if type(self.available) is not bool or not self.skills:
            raise ValueError('Robot needs skills and a boolean availability')
        self.skills = {identifier(k): v if isinstance(v, Belief) else Belief(**v)
                       for k, v in self.skills.items()}


@dataclass
class Goal:
    id: str
    skill: str
    value: float
    description: str = ''
    required: bool = False
    dependencies: list = field(default_factory=list)
    failure_loss: float = 0.0
    execution_cost: float = 0.0
    harm_probability: float = 0.0
    release: float = 0.0
    deadline: Optional[float] = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.skill)
        if type(self.required) is not bool or not isinstance(self.description, str):
            raise ValueError('Invalid goal metadata')
        for name in ('value', 'failure_loss', 'execution_cost', 'release'):
            setattr(self, name, finite(getattr(self, name), name))
        self.harm_probability = finite(self.harm_probability, 'harm_probability', 0, 1)
        if self.deadline is not None:
            self.deadline = finite(self.deadline, 'deadline', self.release)
        if not isinstance(self.dependencies, list) or len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError('Dependencies must be a list without duplicates')
        for item in self.dependencies:
            identifier(item)


@dataclass
class Config:
    risk_budget: float = 0.3
    posterior_tail_probability: float = 0.1
    evidence_decay: float = 0.8
    planning_cost: float = 0.4
    communication_cost: float = 0.1
    delay_cost: float = 0.0
    switching_cost: float = 0.1
    planning_budget: float = 20.0
    fixed_period: float = 2.0
    max_search_nodes: int = 100000

    def __post_init__(self):
        for name in ('risk_budget', 'evidence_decay'):
            setattr(self, name, finite(getattr(self, name), name, 0, 1))
        self.posterior_tail_probability = finite(self.posterior_tail_probability, 'posterior_tail_probability', 1e-9, 1 - 1e-9)
        for name in ('planning_cost', 'communication_cost', 'delay_cost', 'switching_cost', 'planning_budget'):
            setattr(self, name, finite(getattr(self, name), name))
        self.fixed_period = finite(self.fixed_period, 'fixed_period', 1e-9)
        if type(self.max_search_nodes) is not int or self.max_search_nodes < 1:
            raise ValueError('max_search_nodes must be a positive integer')

    @property
    def decision_cost(self):
        return self.planning_cost + self.communication_cost + self.delay_cost


class SearchLimit(RuntimeError):
    pass


class Scheduler:
    """Stateful mission scheduler; feedback and events are explicitly structured."""
    POLICIES = ('fixed', 'event', 'selective')

    def __init__(self, robots, goals, config=None, policy='selective'):
        if policy not in self.POLICIES:
            raise ValueError('Unknown replanning policy')
        robots = [r if isinstance(r, Robot) else Robot(**r) for r in robots]
        goals = [g if isinstance(g, Goal) else Goal(**g) for g in goals]
        if not robots or len(robots) > 8 or len(goals) > 16:
            raise ValueError('Prototype supports 1..8 robots and at most 16 goals')
        if len({r.id for r in robots}) != len(robots) or len({g.id for g in goals}) != len(goals):
            raise ValueError('Duplicate robot or goal identifier')
        self.robots = {r.id: r for r in robots}
        self.goals = {g.id: g for g in goals}
        self.config = config if isinstance(config, Config) else Config(**(config or {}))
        self.policy = policy
        self.protected = {g.id for g in goals if g.required}
        self._check_dependencies()
        self.status = {g.id: 'pending' for g in goals}
        self.active = {}  # robot -> goal; a robot executes at most one goal per wave.
        self.active_charge = {}
        self.risk_reserved = 0.0  # Completed/failed attempts remain charged to mission risk budget.
        self.spent = 0.0
        self.planning_calls = 0
        self.last_plan_time = None
        self.last_time = -1.0
        self.seen_events = {}
        self.emergency_latched = False

    @classmethod
    def from_dict(cls, mission, policy='selective'):
        if not isinstance(mission, dict) or set(mission) - {'robots', 'goals', 'config', 'metadata'}:
            raise ValueError('Invalid mission keys')
        return cls(mission['robots'], mission['goals'], mission.get('config'), policy)

    def _check_dependencies(self):
        visiting, visited = set(), set()

        def visit(goal_id):
            if goal_id not in self.goals or goal_id in visiting:
                raise ValueError('Unknown dependency or dependency cycle')
            if goal_id in visited:
                return
            visiting.add(goal_id)
            for dependency in self.goals[goal_id].dependencies:
                visit(dependency)
            visiting.remove(goal_id)
            visited.add(goal_id)

        for goal_id in self.goals:
            visit(goal_id)
        queue = list(self.protected)
        while queue:
            for dependency in self.goals[queue.pop()].dependencies:
                if dependency not in self.protected:
                    self.protected.add(dependency)
                    queue.append(dependency)

    def _pair(self, robot_id, goal_id):
        robot, goal = self.robots[robot_id], self.goals[goal_id]
        if not robot.available or goal.skill not in robot.skills:
            return None
        belief = robot.skills[goal.skill]
        reward = goal.value * belief.mean - goal.failure_loss * (1 - belief.mean) - goal.execution_cost
        risk = goal.harm_probability * belief.failure_bound(self.config.posterior_tail_probability)
        return reward, risk

    def _ready(self, now):
        return [g for g in self.goals.values() if self.status[g.id] == 'pending'
                and g.release <= now and (g.deadline is None or now < g.deadline)
                and all(self.status[d] == 'completed' for d in g.dependencies)]

    def _score(self, assignment):
        reward, risk, required = 0.0, 0.0, 0
        for robot_id, goal_id in assignment.items():
            pair = self._pair(robot_id, goal_id)
            if pair is None:
                return None
            reward += pair[0]
            risk += max(pair[1], self.active_charge.get(robot_id, 0.0)
                        if self.active.get(robot_id) == goal_id else 0.0)
            required += int(goal_id in self.protected)
            if robot_id in self.active and self.active[robot_id] != goal_id:
                reward -= self.config.switching_cost
        return required, reward, risk

    def _settle(self, goal_id, status):
        self.status[goal_id] = status
        for robot_id, active_goal in list(self.active.items()):
            if active_goal == goal_id:
                self.risk_reserved += self.active_charge.pop(robot_id, 0.0)
                del self.active[robot_id]

    def _validate_event(self, event):
        if not isinstance(event, dict) or set(event) - {
            'id', 'time', 'relevant', 'emergency', 'resume', 'observations',
            'availability', 'completed', 'failed', 'type'}:
            raise ValueError('Invalid event fields')
        identifier(event.get('id', ''))
        now = finite(event.get('time'), 'event time')
        if now < self.last_time:
            raise ValueError('Event time must be monotonic')
        for flag in ('relevant', 'emergency', 'resume'):
            if flag in event and type(event[flag]) is not bool:
                raise ValueError(f'{flag} must be boolean')
        observations = event.get('observations', [])
        availability = event.get('availability', {})
        if not isinstance(observations, list) or not isinstance(availability, dict):
            raise ValueError('Invalid observations or availability')
        for observation in observations:
            if not isinstance(observation, dict) or set(observation) != {'robot', 'skill', 'success'}:
                raise ValueError('Observation must identify robot, skill and boolean outcome')
            robot = self.robots.get(observation['robot'])
            if robot is None or observation['skill'] not in robot.skills or type(observation['success']) is not bool:
                raise ValueError('Unknown capability or non-boolean observation')
        for robot_id, available in availability.items():
            if robot_id not in self.robots or type(available) is not bool:
                raise ValueError('Unknown robot or invalid availability')
        terminal = []
        for key in ('completed', 'failed'):
            items = event.get(key, [])
            if not isinstance(items, list):
                raise ValueError('Feedback must be a goal identifier list')
            for goal_id in items:
                if goal_id not in self.active.values():
                    raise ValueError('Feedback may only settle active goals')
                terminal.append(goal_id)
        if len(set(terminal)) != len(terminal):
            raise ValueError('Conflicting or repeated goal feedback')
        return now

    def _plan(self, now):
        ready = sorted(self._ready(now), key=lambda g: (g.id not in self.protected, -g.value, g.id))
        best_assignment, best_key = {}, (0, 0.0, 0)
        nodes = 0
        remaining_risk = max(0, self.config.risk_budget - self.risk_reserved)

        def search(index, assignment, used, required, reward, risk):
            nonlocal nodes, best_assignment, best_key
            nodes += 1
            if nodes > self.config.max_search_nodes:
                raise SearchLimit('Exact dispatch-wave search limit exceeded')
            if index == len(ready):
                preempted_risk = sum(self.active_charge.get(r, 0.0) for r, g in self.active.items()
                                     if assignment.get(r) != g)
                if risk + preempted_risk > remaining_risk + 1e-12:
                    return
                key = (required, reward, -len(assignment))
                if key > best_key:
                    best_assignment, best_key = dict(assignment), key
                return
            goal = ready[index]
            search(index + 1, assignment, used, required, reward, risk)
            for robot_id in sorted(self.robots):
                if robot_id in used:
                    continue
                pair = self._pair(robot_id, goal.id)
                pair_risk = max(pair[1], self.active_charge.get(robot_id, 0.0)
                                if self.active.get(robot_id) == goal.id else 0.0) if pair else 0.0
                if pair is None or risk + pair_risk > remaining_risk + 1e-12:
                    continue
                gain = pair[0] - (self.config.switching_cost if robot_id in self.active and self.active[robot_id] != goal.id else 0)
                assignment[robot_id] = goal.id
                search(index + 1, assignment, used | {robot_id}, required + int(goal.id in self.protected), reward + gain, risk + pair_risk)
                del assignment[robot_id]

        search(0, {}, set(), 0, 0.0, 0.0)
        return best_assignment, nodes

    def step(self, event):
        # Duplicate delivery is idempotent, before feedback validation.
        if isinstance(event, dict) and isinstance(event.get('id'), str) and event.get('id') in self.seen_events:
            if json.dumps(event, sort_keys=True, allow_nan=False) != self.seen_events[event['id']]:
                raise ValueError('An event identifier was reused with a different payload')
            return self._decision('duplicate', 'Event already processed', 0.0)
        now = self._validate_event(event)  # Validate the complete event before mutating state.
        self.seen_events[event['id']] = json.dumps(event, sort_keys=True, allow_nan=False)
        self.last_time = now
        for key, state in [('completed', 'completed'), ('failed', 'failed')]:
            for goal_id in event.get(key, []):
                deadline = self.goals[goal_id].deadline
                self._settle(goal_id, 'expired' if deadline is not None and now > deadline else state)
        for observation in event.get('observations', []):
            self.robots[observation['robot']].skills[observation['skill']].observe(
                observation['success'], self.config.evidence_decay)
        for robot_id, available in event.get('availability', {}).items():
            self.robots[robot_id].available = available
        if event.get('emergency'):
            self.emergency_latched = True
        elif event.get('resume'):
            self.emergency_latched = False
        for goal in self.goals.values():
            if self.status[goal.id] == 'pending' and goal.deadline is not None and now >= goal.deadline:
                self._settle(goal.id, 'expired')
        # Failure of a prerequisite makes descendants explicitly unreachable.
        for _ in self.goals:
            for goal in self.goals.values():
                if self.status[goal.id] == 'pending' and any(self.status[d] in {'failed', 'expired', 'abandoned', 'unreachable'} for d in goal.dependencies):
                    self.status[goal.id] = 'unreachable'
        old = self._score(self.active)
        unsafe = old is None or (old is not None and self.risk_reserved + old[2] > self.config.risk_budget + 1e-12)
        stopped = []
        if self.emergency_latched or unsafe:
            stopped = list(self.active)
            self.risk_reserved += sum(self.active_charge.values())
            self.active = {}
            self.active_charge = {}
            if self.emergency_latched:
                return self._decision('stop', 'Emergency latched; explicit resume required', 0, stopped=stopped)
            old = (0, 0.0, 0.0)

        ready = self._ready(now)
        # An inexpensive relaxed bound ignores robot conflicts and joint risk.
        relaxed = sum(max([0.0] + [p[0] for r in self.robots if (p := self._pair(r, g.id)) is not None]) for g in ready)
        improvement_bound = relaxed - old[1]
        required_upper = min(
            sum(r.available for r in self.robots.values()),
            sum(g.id in self.protected and any(self._pair(r, g.id) is not None for r in self.robots)
                for g in ready),
        )
        urgent = unsafe or not self.active or required_upper > old[0]
        if not ready:
            return self._decision('stop' if stopped else 'keep', 'No dispatchable subgoals', improvement_bound, stopped=stopped)
        if (self.policy == 'selective' and not self.active
                and not any(g.id in self.protected for g in ready)
                and relaxed <= self.config.decision_cost):
            for goal in ready:
                self.status[goal.id] = 'abandoned'
            return self._decision('abandon', 'Optional dispatch value does not cover replanning cost',
                                  improvement_bound, stopped=stopped)
        # Do not spend planning budget repeatedly proving the same elementary
        # impossibility (e.g. all robots unavailable). A real observation or
        # availability change can make this check pass on a later event.
        remaining_risk = max(0, self.config.risk_budget - self.risk_reserved)
        feasible_pair = any(
            pair is not None and pair[1] <= remaining_risk + 1e-12
            and (g.id in self.protected or pair[0] > 0)
            for g in ready for robot_id in self.robots
            for pair in [self._pair(robot_id, g.id)]
        )
        if not self.active and not feasible_pair:
            return self._decision('stop' if stopped else 'keep',
                                  'No feasible capability under remaining risk budget',
                                  improvement_bound, stopped=stopped)
        triggered = self.last_plan_time is None
        if self.policy == 'fixed':
            triggered |= self.last_plan_time is None or now - self.last_plan_time >= self.config.fixed_period
        elif self.policy == 'event':
            triggered |= event.get('relevant', False) or bool(event.get('completed') or event.get('failed'))
        else:
            triggered |= urgent or improvement_bound > self.config.decision_cost
        # Safety is enforced separately even when a fixed/event trigger is absent.
        triggered |= unsafe
        if not triggered:
            return self._decision('keep', 'Replanning trigger not met', improvement_bound, stopped=stopped)
        if self.spent + self.config.decision_cost > self.config.planning_budget + 1e-12:
            return self._decision('stop' if stopped else 'keep', 'Planning budget exhausted', improvement_bound, stopped=stopped)

        self.spent += self.config.decision_cost
        self.planning_calls += 1
        self.last_plan_time = now
        try:
            candidate, nodes = self._plan(now)
        except SearchLimit:
            return self._decision('stop' if stopped else 'keep', 'Search budget exhausted; retained safe incumbent', improvement_bound, stopped=stopped, exact=False)
        score = self._score(candidate)
        # The relaxed bound may overestimate gains. Keep the incumbent when the
        # exact candidate has no net benefit, but account for the planning cost.
        install = urgent or self.policy != 'selective' or score[0] > old[0] or score[1] - old[1] > self.config.decision_cost
        if install:
            for goal in ready:
                if goal.id in candidate.values() or goal.id in self.protected:
                    continue
                pairs = [p for r in self.robots if (p := self._pair(r, goal.id)) is not None]
                # Scarce capacity alone defers a goal; it does not abandon it.
                if pairs and all(p[0] <= 0 for p in pairs):
                    self.status[goal.id] = 'abandoned'
            previous = dict(self.active)
            for robot_id, old_goal in previous.items():
                if candidate.get(robot_id) != old_goal:
                    self.risk_reserved += self.active_charge.pop(robot_id, 0.0)
            self.active = candidate
            self.active_charge = {
                r: max(self.active_charge.get(r, 0.0), self._pair(r, g)[1])
                for r, g in candidate.items()
            }
            stopped = sorted(set(stopped) | {r for r in previous if previous.get(r) != candidate.get(r)})
        return self._decision('replan' if install else 'keep', 'Exact dispatch wave evaluated', improvement_bound, stopped=stopped, search_nodes=nodes)

    def _decision(self, action, reason, improvement_bound, stopped=None, exact=True, search_nodes=0):
        score = self._score(self.active)
        return {'action': action, 'reason': reason, 'time': self.last_time,
                'assignments': dict(self.active), 'stopped_robots': stopped or [],
                'status': dict(self.status), 'planning_calls': self.planning_calls,
                'replanning_calls': max(0, self.planning_calls - 1),
                'planning_cost_units': self.spent,
                'risk_reserved': self.risk_reserved,
                'active_risk_score': score[2] if score else None,
                'improvement_upper_bound': improvement_bound,
                'search_nodes': search_nodes, 'exact_wave_search': exact}

    def proposed_robot_tasks(self):
        return {'robot_tasks': {r: self.goals[g].description or g for r, g in self.active.items()},
                'sequence': '', 'goal_ids': dict(self.active), 'preview_only': True}
