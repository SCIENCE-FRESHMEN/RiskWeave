#!/usr/bin/env bash
# ROS setup scripts intentionally read optional unset environment variables.
set -eo pipefail
source /opt/ros/humble/setup.bash
mkdir -p /ws/src /output
cp -a /work/riskweave/. /ws/src/
python3 -B /work/tools/prepare_fortress_assets.py --source /ws/src --apply --output /output/fortress_overlay.json
colcon --log-base /output/colcon-log build --base-paths /ws/src --build-base /ws/build --install-base /ws/install --executor sequential
source /ws/install/setup.bash
python3 -B /work/tools/container_ros_smoke.py
python3 -B /work/tools/container_gazebo_smoke.py
