"""Launch file for bringing up the EduBot nodes:
- bridge.launch.py: Launches the serial bridge and wheel odometry.
- description.launch.py: Launches the robot_state_publisher and joint_state_publisher.

"""

import os

from ament_index_python.packages import get_package_share_directory
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

from launch import LaunchDescription

# Path to package share directory
edubot_share_dir = get_package_share_directory("edubot")


# Serial bridge and wheel odometry node - handles PRIZM communication and publishes joint states and odometry
def edubot_bridge():
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(edubot_share_dir, "launch", "bridge.launch.py")])
    )


# Robot description nodes - Loads URDF and publishes robot_state_publisher
def edubot_description():
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(edubot_share_dir, "launch", "description.launch.py")])
    )


# 2D LiDAR node - LDS01 2D LiDAR driver
def lds01_lidar():
    # Find the package directory for the LDS01 driver
    lds01_share_dir = get_package_share_directory("hls_lfcd_lds_driver")
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(lds01_share_dir, "launch", "hlds_laser.launch.py")]),
        launch_arguments={"port": "/dev/edubot_lidar"}.items(),
    )


# 2D LiDAR filter node - filters out bad points from LDS01 data
def lds01_lidar_filter():
    return Node(
        package="laser_filters",
        executable="scan_to_scan_filter_chain",
        name="laser_scan_filter",
        output="screen",
        parameters=[
            edubot_share_dir + "/config/scan_filter.yaml",
        ],
        remappings=[
            ("scan", "/scan"),  # input raw scan
            ("scan_filtered", "/scan_filtered"),  # output cleaned scan
        ],
        respawn=True,
        respawn_delay=2.0,
    )


# USB camera node - usb_cam driver (https://github.com/ros-drivers/usb_cam)
def usb_camera():
    return Node(
        package="usb_cam",
        executable="usb_cam_node_exe",
        name="usb_cam_node",
        parameters=[edubot_share_dir + "/config/camera_params.yaml"],  # CHANGE ONLY THIS .yaml FOR CAMERA PARAMETERS
        output="screen",
        # Restart policy for robustness
        respawn=True,
        respawn_delay=10.0,
    )


# IMU node - BMI088 6-axis IMU driver
def imu_node():
    imu_driver_share_dir = get_package_share_directory("imu_serial_to_ros_publisher")
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(imu_driver_share_dir, "launch", "imu_publisher.launch.py")]),
        launch_arguments={
            "serial_port": "/dev/edubot_imu",
            "frame_id": "imu_link",
        }.items(),
    )


# IMU filter node - Madgwick filter for IMU data, publishes filtered orientation with raw imu data
def imu_filter():
    return Node(
        package="imu_filter_madgwick",
        executable="imu_filter_madgwick_node",
        name="imu_filter",
        output="screen",
        parameters=[edubot_share_dir + "/config/imu_filter.yaml"],
        remappings=[
            ("imu/data_raw", "/imu/data_raw"),  # Input topic from IMU node
            ("imu/data", "/imu/data_filtered"),  # Output topic for filtered IMU data
            # ("imu/mag", "/imu/mag"),  # Add if using Magnetometer data topic
        ],
        # Restart policy for robustness
        respawn=True,
        respawn_delay=2.0,
    )


# Robot Localization with Extended Kalman Filter (EKF) - fuses odometry with filtered IMU
# Published tf between "odom" and "base_footprint" frames
def ekf_odom():
    return Node(
        package="robot_localization",
        executable="ekf_node",
        name="ekf_filter_node",
        output="screen",
        parameters=[edubot_share_dir + "/config/ekf.yaml"],
        # Restart policy for robustness
        respawn=True,
        respawn_delay=2.0,
    )


# SLAM node - SLAM Toolbox for online(incremental mapping) asynchronous(multi-threaded) SLAM
def slam_toolbox():
    slam_toolbox_share_dir = get_package_share_directory("slam_toolbox")
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(slam_toolbox_share_dir, "launch", "online_async_launch.py")]),
        launch_arguments={
            "use_sim_time": "false",
            "slam_params_file": os.path.join(edubot_share_dir, "config", "slam_toolbox_online_async.yaml"),
        }.items(),
    )


def generate_launch_description():
    """
    Generate the launch description for bringing up the EduBot nodes.

    Returns:
        LaunchDescription containing all necessary nodes for the EduBot.
    """
    ld = LaunchDescription()
    ld.add_action(edubot_bridge())
    ld.add_action(edubot_description())
    ld.add_action(lds01_lidar())
    ld.add_action(lds01_lidar_filter())
    ld.add_action(usb_camera())
    ld.add_action(imu_node())
    ld.add_action(imu_filter())
    ld.add_action(ekf_odom())
    # Defer SLAM Toolbox startup to allow other nodes to initialize first
    ld.add_action(TimerAction(period=5.0, actions=[slam_toolbox()]))
    return ld
