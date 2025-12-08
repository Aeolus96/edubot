
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

# Initialize rosdep (only the first time):
sudo rosdep init
rosdep update

# Create a ROS workspace if you haven't and clone the edu packages into ~/ros2_ws/src:
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src

# Main robot package
git clone https://github.com/Aeolus96/edubot.git

# IMU serial publisher (optional for EduBot)
git clone https://github.com/Aeolus96/imu_serial_to_ros_publisher.git
```

### Install dependencies

```bash
# From the workspace root run:
cd ~/ros2_ws
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

>NOTE: `rosdep` maps package dependencies declared in `package.xml` to system packages. It will try to install ROS packages (via apt) and system libraries. For Python packages, rosdep will either install apt-packaged Python libraries or you may need to install with `pip` (see next step). Some packages may need to be manually installed with `apt` as well.

```bash
# For installing Python packages with `pip` use a virtual environment (recommended for Ubuntu 24.04):

# Create a virtual environment named `jazzy`
cd ~/
python3 -m venv jazzy --system-site-packages

# Activate the virtual environment by sourcing the `activate` script
source ~/jazzy/bin/activate

# The `edubot` package includes a `requirements.txt` file. Install it with pip:
python3 -m pip install -r src/edubot/requirements.txt

# Now install these apt packages specific to our ROS 2 distro to make sure all package dependencies are met:
sudo apt install ros-jazzy-hls-lfcd-lds-driver* ros-jazzy-navigation2 ros-jazzy-nav2-* ros-jazzy-usb-cam* ros-jazzy-robot-state-publisher* ros-jazzy-joint-* ros-jazzy-xacro ros-jazzy-imu-* ros-jazzy-robot-localization* ros-jazzy-teleop-t* ros-jazzy-tf2* ros-jazzy-rqt* ros-jazzy-rviz* ros-jazzy-laser* ros-jazzy-sick-scan-xd*
```

>IMPORTANT: Always run the next commands from the workspace root as shown. If you run it from anywhere else, it will not work and it will create a broken workspace. To fix, remove all `build`, `install` and `log` folders from the workspace. Re-open the terminal and run the command from the workspace root.

```bash
# Then build and source the workspace (this will be necessary commands if you make any changes to the code):
cd ~/ros2_ws
colcon build --symlink-install
# Then source the workspace to use the packages in that workspace:
source ~/ros2_ws/install/setup.bash
```

### TIP: configure your shell (a.k.a. terminal)

If you plan to use the same workspace often, add the `source` line to your `~/.bashrc` file. You can also create aliases in the `~/.bashrc` file for common commands used very often with ROS2

```bash
alias ros2_source="source ~/ros2_ws/install/setup.bash"
alias ros2_build="cd ~/ros2_ws && colcon build --symlink-install && ros2_source"
# Now you can directly type `ros2_source` or `ros2_build` in the terminal to execute the aliased commands
```

This will make it easier to build and source the workspace when making changes to the code that needs compilation.

## Device permissions and stable /dev (UART) links

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

# then reload udev rules and trigger (requires replugging devices to take effect):
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

From any workspace sourced shell run one of the provided launch files:

```bash
# Start entire robot's ROS 2 stack with default parameters
ros2 launch edubot edubot.launch.py

# Start robot stack with SLAM enabled for online mapping
ros2 launch edubot edubot.launch.py slam:=True

# Start with pre-built map for localization only
ros2 launch edubot edubot.launch.py slam:=False map:=/path/to/map.yaml
```

### Available launch files

- `edubot.launch.py` — Main launch file; starts all robot subsystems (serial bridge, odometry, LiDAR, camera, EKF, and navigation)
- `bridge.launch.py` — Launches the serial bridge (`edubot_serial_bridge`) and wheel odometry node (`edubot_wheel_odom`)
- `description.launch.py` — Launches `robot_state_publisher` and `joint_state_publisher` for robot URDF and transforms
- `nav2_bringup_launch.py` — Navigation2 configuration with support for SLAM or localization modes
- `nav2_slam_launch.py` — Launches SLAM Toolbox for online mapping
- `nav2_localization_launch.py` — Launches Nav2 localization against a pre-built map
- `nav2_navigation_launch.py` — Launches Nav2 navigation stack

## Nodes and topics

### Core EduBot nodes

- **`edubot_serial_bridge`** — Manages communication with PRIZM motor controller over serial (COBS protocol)
  - Subscribes: `/cmd_vel` (geometry_msgs/Twist)
  - Publishes: `/joint_states` (sensor_msgs/JointState), `/battery_state` (sensor_msgs/BatteryState)
  
- **`edubot_wheel_odom`** — Computes odometry from wheel encoders using differential drive kinematics
  - Subscribes: `/joint_states` (sensor_msgs/JointState)
  - Publishes: `/wheel/odometry` (nav_msgs/Odometry), broadcasts `odom→base_link` TF transform
  
- **`usb_cam_node`** — Publishes video stream from USB camera
  - Publishes: `/image_raw` (sensor_msgs/Image), `/camera_info` (sensor_msgs/CameraInfo)

- **`sick_tim_5xx`** — 2D LiDAR driver (SICK TiM561)
  - Publishes: `/scan` (sensor_msgs/LaserScan)

### Supporting nodes (from dependencies)

- **IMU publisher node** — From `imu_serial_to_ros_publisher` package (if installed)
  - Publishes: `imu/data_raw` (sensor_msgs/Imu)

- **`imu_filter_madgwick`** — Fuses raw IMU data using Madgwick filter
  - Subscribes: `imu/data_raw`
  - Publishes: `imu/data` (sensor_msgs/Imu)

- **`ekf_node`** (robot_localization) — Fuses odometry from wheels, IMU, and other sensors
  - Subscribes: `/wheel/odometry`, `imu/data`
  - Publishes: `/odometry/filtered` (nav_msgs/Odometry), broadcasts `odom→base_link` TF

- **`robot_state_publisher`** — Publishes robot URDF and static transforms
  - Publishes: `/robot_description`, `/tf_static`

- **`joint_state_publisher`** — Visualizes joint angles in RViz

- **Nav2 nodes** — Navigation2 stack for autonomous navigation
  - Includes planners, controllers, and recovery behaviors

## Configuration files

- `config/camera_info.yaml` — Camera calibration data (intrinsics and distortion)
- `config/camera_params.yaml` — USB camera driver parameters (resolution, frame rate, etc.)
- `config/nav2_params.yaml` — Navigation2 stack parameters (costmaps, planners, controllers)
- `config/ekf.yaml` — EKF (Extended Kalman Filter) node configuration for sensor fusion
- `config/imu_filter.yaml` — Madgwick IMU filter parameters
- `config/scan_filter.yaml` — Laser scan filter configuration

## Robot description

- `urdf/edubot.urdf` — Robot URDF model defining kinematics, links, joints, and collision geometry
- `meshes/` — Visual 3D mesh files for RViz visualization
- `rviz/edubot.rviz` — Pre-configured RViz layout and visualization settings

## Maps

- `maps/m215a_saved_map.yaml` — Navigation2 map metadata
- `maps/m215a_saved_map.pgm` — Occupancy grid map image
- `maps/m215a_serialized_map.posegraph` — SLAM Toolbox pose graph (for loop closure)

## License and contributing

Created by [Devson Butani](https://github.com/Aeolus96), 2025

MIT License. See `LICENSE` file for details.

Contributing bug fixes and new features? Submit a pull request!
