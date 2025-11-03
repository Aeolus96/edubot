# EduBot ROS2 Package

ROS2 package for EduBot v2 developed for ROS classes at LTU. This package provides the necessary drivers, launch files, and utilities to operate the EduBot platform.

## Prerequisites

- Ubuntu 24.04 (Noble Numbat)
- ROS2 Jazzy Jellyfish (Desktop Install)

This package works together with the `imu_serial_to_ros_publisher` package to provide full robot functionality:
- `edubot`: Main robot package with motor control, odometry, and robot description
- `imu_serial_to_ros_publisher`: Handles IMU sensor data for improved navigation accuracy

  ```bash
  # Add ROS2 apt repository
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
  
  # Update package list and install ROS2
  sudo apt update
  sudo apt install ros-jazzy-desktop
  ```

## Installation

1. Install development tools and ROS2 dependencies:

```bash
sudo apt update
sudo apt install -y python3-pip python3-rosdep python3-colcon-common-extensions git
```

2. Initialize rosdep if you haven't already:

```bash
sudo rosdep init
rosdep update
```

3. Create a ROS2 workspace:

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

4. Clone the required repositories:

```bash
# Clone the main EduBot package
git clone https://github.com/Aeolus96/edubot.git

# Clone the IMU package (required for EduBot operation)
git clone https://github.com/Aeolus96/imu_serial_to_ros_publisher.git
```

5. Install all dependencies automatically:

```bash
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

This command will automatically install:

- All required ROS2 packages (slam_toolbox, usb_cam, etc.)
- Python packages (pyserial, etc.)
- System dependencies

4. Build the workspace:

```bash
colcon build --symlink-install
```

5. Source the workspace:

```bash
source ~/ros2_ws/install/setup.bash
```

6. Set up device permissions:

```bash
cd ~/ros2_ws/src/edubot
python3 edubot_udev_setup.py
```

## Launch Files

The package provides several launch files for different functionalities:

### Basic Bridge Launch

Launches the serial communication bridge and wheel odometry:

```bash
ros2 launch edubot bridge.launch.py
```

### Robot Description Launch

Launches the robot state publisher with URDF:

```bash
ros2 launch edubot description.launch.py
```

### Complete Bringup

Launches all necessary nodes for full robot operation:

```bash
ros2 launch edubot bringup.launch.py
```

This includes:

- Serial bridge and wheel odometry
- Robot description and state publisher
- LDS01 2D LiDAR
- USB Camera
- IMU node
- IMU filter
- EKF odometry
- SLAM Toolbox

## Node Information

### edubot_serial_bridge

- Subscribes to: `/cmd_vel` (geometry_msgs/Twist)
- Publishes:
  - `/joint_states` (sensor_msgs/JointState)
  - `/battery_state` (sensor_msgs/BatteryState)

### edubot_wheel_odom

- Subscribes to: `/joint_states` (sensor_msgs/JointState)
- Publishes: `/odom` (nav_msgs/Odometry)

## Configuration

Configuration files are located in the `config/` directory:

- `camera_info.yaml`: Camera calibration parameters
- `camera_params.yaml`: USB camera parameters
- `ekf.yaml`: Extended Kalman Filter parameters
- `imu_filter.yaml`: IMU filter parameters
- `slam_toolbox_online_async.yaml`: SLAM configuration

## License

This project is licensed under the MIT License - see the LICENSE file for details
