# RiskWeave

RiskWeave is an experimental framework for risk aware reasoning of large language model agents

![]([https://img.shields.io/badge/Python-3.10+-brightgreen](https://img.shields.io/badge/Python-3.10+-brightgreen))
![]([https://img.shields.io/badge/Agent-Risk-Reasoning-blue](https://img.shields.io/badge/Agent-Risk-Reasoning-blue))
![]([https://img.shields.io/badge/Planning-Verification-orange](https://img.shields.io/badge/Planning-Verification-orange))
![]([https://img.shields.io/badge/Open-For-Research-important](https://img.shields.io/badge/Open-For-Research-important))
  

## project introduction

Large language model agents generate action sequences for sequential decision tasks without explicit risk assessment. Agents may select high risk actions that cause irreversible state damage and task failure. Existing planning frameworks focus on task completion only and lack systematic risk modeling and intervention mechanisms. This framework builds risk representation risk prediction and risk mitigation modules into agent planning loops. It supports dynamic risk estimation before action execution and adjusts agent behavior according to estimated risk levels.

This repository contains the full implementation of risk modeling action risk scoring planning intervention and multi environment evaluation pipelines. Researchers can deploy the framework on standard agent benchmarks and conduct ablation experiments for risk reasoning strategies.

## core features

unified risk representation for sequential agent actions
the framework encodes task state action effect and historical failure information into structured risk features. It outputs continuous risk scores for candidate actions before execution
inline planning adjustment based on risk feedback
the planner filters or rearranges candidate actions when estimated risk exceeds preset thresholds. The agent avoids dangerous paths instead of directly executing all generated plans
compatible with common agent benchmark environments
the environment adapter layer supports standard interactive task benchmarks. Users can run risk reasoning on top of existing agent backends without heavy modification
structured risk logging and analysis tools
the system records action risk scores trigger conditions and final task outcomes. It aggregates risk statistics to reveal the correlation between agent risk estimation and actual failure
decoupled module design for algorithm extension
risk predictor scoring function and planning intervention policy are separated. New risk estimation methods can be plugged into the framework with minimal adaptation work

## performance overview

vanilla agents execute plans without risk awareness and frequently enter unrecoverable states in high constraint tasks
agents integrated with RiskWeave reduce the proportion of high risk actions during planning. Task completion stability improves especially for long horizon sequential tasks
the framework maintains comparable reasoning overhead against plain planning baselines. It avoids large extra token consumption

this repository fits researchers studying agent safety planning verification and uncertainty aware decision making for large model agents

## quick start

### environment setup

```
git clone [https://github.com/SCIENCE-FRESHMEN/RiskWeave.git](https://github.com/SCIENCE-FRESHMEN/RiskWeave.git)
cd RiskWeave

pip install -r requirements.txt

python scripts/download_benchmark.py
```

### run evaluation

```
python run_eval.py --config configs/default_risk_planner.yaml

python run_eval.py --config configs/baseline_no_risk.yaml
```

evaluation results risk logs and statistical reports are saved to ./output

## repository structure

```
RiskWeave
├── agent
│   ├── risk_model.py
│   └── risk_planner.py
├── env_adapter
├── configs
├── scripts
├── run_eval.py
└── output
```

## target users

researchers working on large language model agent safety and robust planning
researchers studying risk estimation and uncertainty reasoning in sequential decision tasks
researchers needing a testbed to verify risk intervention strategies for agents
researchers collecting high risk action samples to analyze agent failure modes

## limitation

risk prediction relies on observable state features. Hidden risks with insufficient state evidence cannot be reliably identified. More accurate risk predictors can be submitted through pull requests

## citation

```
@misc{RiskWeave,
  title={RiskWeave: A Framework for Risk Aware Reasoning of Large Language Model Agents},
  author={SCIENCE-FRESHMEN},
  year={2026},
  howpublished={\url{[https://github.com/SCIENCE-FRESHMEN/RiskWeave.git](https://github.com/SCIENCE-FRESHMEN/RiskWeave.git)}}
}
```

## contributing

users can submit issues for bugs and pull requests for new risk models intervention policies or benchmark adapters

## license

MIT License
