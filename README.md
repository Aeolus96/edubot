
# EduBot ROS 2 Package

EduBot is a ROS 2 package that provides robot description, drivers, and bringup for the EduBot platform. It includes:

- Serial bridge to the PRIZM motor controller
- Wheel odometry
- IMU integration and Madgwick filter
- USB camera support
- 2D LiDAR driver
- EKF-based odometry
- SLAM Toolbox

This README assumes you are using Ubuntu 24.04 and ROS 2 Jazzy.

## Quick build requirements

- Target OS: Ubuntu 24.04 (Noble Numbat)
- Target ROS 2: Jazzy Jellyfish (desktop)
- Python: system Python 3.12

## Install from source

```bash
# Source the ROS 2 setup in every new shell (or add to your shell rc):
source /opt/ros/jazzy/setup.bash
```

```bash
# Initialize rosdep (only the first time):
sudo rosdep init
rosdep update
```

```bash
# Create a ROS workspace if you haven't and clone the edu packages into ~/ros2_ws/src:
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src

# Main robot package
git clone https://github.com/Aeolus96/edubot.git

# IMU serial publisher (required by EduBot)
git clone https://github.com/Aeolus96/imu_serial_to_ros_publisher.git
```

### Install dependencies

```bash
# From the workspace root run:
cd ~/ros2_ws
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

>`rosdep` maps package dependencies declared in `package.xml` to system packages. It will try to install ROS packages (via apt) and system libraries. For Python packages, rosdep will either install apt-packaged Python libraries or you may need to install with `pip` (see next step).

For installing Python packages with `pip` use a virtual environment (recommended for Ubuntu 24.04):

```bash
# Create a virtual environment named `jazzy`
cd ~/
python3 -m venv jazzy --system-site-packages
source ~/jazzy/bin/activate
```

```bash
# Both packages include `requirements.txt` files. Install them with pip:
python3 -m pip install --user -r src/edubot/requirements.txt
python3 -m pip install --user -r src/imu_serial_to_ros_publisher/requirements.txt
```

>Using `--user` keeps installs local to your account (Recommended over using `--break-system-packages`).

```bash
# Build and source the workspace
cd ~/ros2_ws
colcon build --symlink-install
source ~/ros2_ws/install/setup.bash
```

### TIP: configure your shell (a.k.a. terminal)

If you plan to use the workspace often, add the `source` line to your `~/.bashrc`. You can also create aliases in the `~/.bashrc` file for common commands used very often with ROS2

```bash
alias ros2_source="source ~/ros2_ws/install/setup.bash"
alias ros2_build="cd ~/ros2_ws && colcon build --symlink-install && ros2_source"
```

This will make it easier to build and source the workspace when making changes to the code that needs compilation.

## Device permissions and stable /dev links

EduBot uses stable symlinks for devices so launch files don't depend on volatile `/dev/ttyUSB*` names when multiple devices are connected. Expected device paths are:

- PRIZM motor controller: `/dev/edubot_prizm`
- 2D LiDAR: `/dev/edubot_lidar`
- USB camera: `/dev/edubot_camera`
- IMU: `/dev/edubot_imu`

Create these links with the interactive helper script shipped in the edubot package:

```bash
cd ~/ros2_ws/src/edubot
# Option 2 in this interactive script is recommended and it automatically adds `edubot_` before the symlink
python3 edubot_udev_setup.py

# then reload udev rules and trigger
sudo udevadm control --reload
sudo udevadm trigger

# After replugging devices wait a few seconds, then verify links exist:
ls -l /dev/edubot_*

# Also ensure your user is in the proper groups:
sudo usermod -aG dialout $USER   # serial devices
sudo usermod -aG video $USER     # cameras
# then log out and back in (or reboot)
```

## Launch examples

From any sourced shell run one of the provided launch files:

```bash
# Start serial bridge and wheel odometry
ros2 launch edubot bridge.launch.py

# Robot URDF description (robot_state_publisher)
ros2 launch edubot description.launch.py

# Full bringup (LiDAR, camera, IMU, EKF, SLAM Toolbox)
ros2 launch edubot bringup.launch.py
```

## Nodes and topics

- `edubot_serial_bridge` — subscribes `/cmd_vel`, publishes `/joint_states` and `/battery_state`.
- `edubot_wheel_odom` — subscribes `/joint_states`, publishes `/wheel/odometry`.
- IMU node — provided by `imu_serial_to_ros_publisher`, publishes `imu/data_raw`.

## Configuration files

- `config/camera_params.yaml` — USB camera params
- `config/ekf.yaml` — robot_localization configuration
- `config/imu_filter.yaml` — Madgwick filter parameters
- `config/slam_toolbox_online_async.yaml` — SLAM Toolbox tuning

## License and contributing

Created by [Devson Butani](https://github.com/Aeolus96), 2025

MIT License. See `LICENSE` file for details.

Contributing bug fixes and new features? Submit a pull request!
