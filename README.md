
# EduBot ROS 2 Package

EduBot is a ROS 2 package that provides robot description, drivers, and bringup for the EduBot platform. It includes:

- Serial bridge to the PRIZM motor controller
- Wheel odometry with encoder-based pose estimation
- SICK TiM561 2D LiDAR driver
- USB camera support (dual camera capable)
- EKF-based odometry fusion (wheel odometry; IMU support is available but currently disabled)
- Navigation2 stack with SLAM Toolbox support for mapping and navigation
- URDF robot model and RViz visualization

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

### Start only core robot services (bridge, odometry, LiDAR, cameras, EKF) without navigation

```bash
ros2 launch edubot edubot.launch.py
```

### Start entire robot stack with Nav2 and SLAM enabled for online mapping

```bash
ros2 launch edubot edubot.launch.py nav2:=True slam:=True
```

### Start entire robot stack with Custom Navigation and slam enabled for online mapping

```bash
ros2 launch edubot edubot.launch.py nav2:=True slam:=True localization_only:=True
```

### Start robot stack with Nav2 and pre-built map for localization

```bash
ros2 launch edubot edubot.launch.py nav2:=True slam:=False map:=/path/to/map.yaml
```

### Start robot stack with Custom Navigation and pre-built map for localization only

```bash
ros2 launch edubot edubot.launch.py nav2:=True slam:=False localization_only:=True map:=/path/to/map.yaml
```

### Available launch files

- `edubot.launch.py` — Main launch file; starts core robot subsystems (serial bridge, odometry, LiDAR, cameras if present, and EKF). Add `nav2:=True` to enable Navigation2 stack.
- `bridge.launch.py` — Launches the serial bridge (`edubot_serial_bridge`) and wheel odometry node (`edubot_wheel_odom`)
- `description.launch.py` — Launches `robot_state_publisher` and `joint_state_publisher` for robot URDF and transforms
- `nav2_bringup_launch.py` — Navigation2 stack configuration with support for SLAM or localization modes
- `nav2_slam_launch.py` — Launches SLAM Toolbox for online mapping
- `nav2_localization_launch.py` — Launches Nav2 localization against a pre-built map
- `nav2_navigation_launch.py` — Launches Nav2 navigation stack
- `no_nav2_bringup_launch.py` — Launches SLAM/localization only (without Nav2 planning and collision avoidance for custom navigation implementations)

## Nodes and topics

### Core EduBot nodes

- **`edubot_serial_bridge`** — Manages communication with PRIZM motor controller over serial (COBS protocol)
  - Subscribes: `/cmd_vel` (geometry_msgs/Twist)
  - Publishes: `/joint_states` (sensor_msgs/JointState), `/battery_state` (sensor_msgs/BatteryState)
  
- **`edubot_wheel_odom`** — Computes odometry from wheel encoders using differential drive kinematics
  - Subscribes: `/joint_states` (sensor_msgs/JointState)
  - Publishes: `/wheel/odometry` (nav_msgs/Odometry), broadcasts `odom→base_footprint` TF transform
  
- **`usb_cam_node` (camera_1, camera_2)** — Publishes video stream from USB cameras
  - Publishes: `/camera_{1,2}/image_raw` (sensor_msgs/Image), `/camera_{1,2}/camera_info` (sensor_msgs/CameraInfo)
  - Cameras are launched dynamically only if `/dev/edubot_camera_1` and/or `/dev/edubot_camera_2` exist

- **`sick_tim561_lidar`** — SICK TiM561 2D LiDAR driver (hardwired to IP 192.168.71.71)
  - Publishes: `/scan` (sensor_msgs/LaserScan)

### Supporting nodes (from dependencies)

- **IMU publisher node** — From `imu_serial_to_ros_publisher` package (currently disabled; was for BMI088 6-axis IMU)
  - Publishes: `imu/data_raw` (sensor_msgs/Imu)

- **`imu_filter_madgwick`** — Madgwick filter for fusing raw IMU data (currently disabled)
  - Subscribes: `imu/data_raw`
  - Publishes: `imu/data` (sensor_msgs/Imu)

- **`ekf_node`** (robot_localization) — Fuses odometry from wheels (IMU support available but currently disabled)
  - Subscribes: `/wheel/odometry`
  - Publishes: `/odometry/filtered` (nav_msgs/Odometry), broadcasts `odom→base_footprint` TF

- **`robot_state_publisher`** — Publishes robot URDF and static transforms
  - Publishes: `/robot_description`, `/tf_static`

- **`joint_state_publisher`** — Visualizes joint angles in RViz

- **Nav2 nodes** — Navigation2 stack for autonomous navigation (optional; launch with `nav2:=True`)
  - Includes planners, controllers, and recovery behaviors
  - Can run in full autonomous mode or localization-only mode (see launch examples)

## Configuration files

- `config/camera_1_params.yaml` — USB camera 1 driver parameters (resolution, frame rate, etc.)
- `config/camera_2_params.yaml` — USB camera 2 driver parameters (if dual camera setup is used)
- `config/camera_info.yaml` — Camera calibration data reference (intrinsics and distortion)
- `config/nav2_params.yaml` — Navigation2 stack parameters (costmaps, planners, controllers)
- `config/ekf.yaml` — EKF (Extended Kalman Filter) node configuration for sensor fusion on wheel odometry
- `config/imu_filter.yaml` — Madgwick IMU filter parameters (currently disabled)
- `config/scan_filter.yaml` — Laser scan filter configuration (used with LDS01; not needed for SICK TiM561)
- `config/teleop.yaml` — Teleop joystick and keyboard parameters (launch files for these nodes are commented out)

## Robot description

- `urdf/edubot.urdf` — Robot URDF model defining kinematics, links, joints, and collision geometry
- `meshes/` — Visual 3D mesh files for RViz visualization
- `rviz/edubot.rviz` — Pre-configured RViz layout and visualization settings

## Maps

Pre-built maps available in `maps/` directory:

- `J234_maze.yaml` / `J234_maze.pgm` — Maze environment (default map loaded by launchers)
- `J234.yaml` / `J234.pgm` — Alternate J234 environment map
- `m215a_saved_map.yaml` / `m215a_saved_map.pgm` — M215A laboratory environment
- `m215a_serialized_map.posegraph` — SLAM Toolbox pose graph for M215A map (for loop closure detection)

## License and contributing

Created by [Devson Butani](https://github.com/Aeolus96), 2025

MIT License. See `LICENSE` file for details.

Contributing bug fixes and new features? Submit a pull request!
