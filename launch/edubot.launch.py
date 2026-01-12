"""Launch file for starting everything up for the EduBot:
- bridge.launch.py: Launches the serial bridge and wheel odometry.
- description.launch.py: Launches the robot_state_publisher and joint_state_publisher.
- sick_tim_5xx.launch: Launches the SICK TiM561 2D LiDAR driver node.
- usb_cam_node: Launches the USB camera driver node.
- ekf.launch.py: Launches the robot_localization EKF node for odometry fusion.
- nav2_bringup_launch.py: Launches the Nav2 stack with SLAM or localization based on arguments.

Usage:
    ros2 launch edubot edubot.launch.py [slam:=True|False] [map:=/path/to/map.yaml] [use_sim_time:=True|False]
Arguments:
    slam: Whether to launch SLAM Toolbox for mapping (default: False).
    map: Full path to the map YAML file for localization (default: edubot/maps/m215a_saved_map.yaml).
    use_sim_time: Whether to use simulation time (default: False).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from launch import LaunchDescription

# Path to package share directory
edubot_share_dir = get_package_share_directory("edubot")


# Declare Launch arguments
declare_use_sim_time = DeclareLaunchArgument("use_sim_time", default_value="False", description="Use simulation clock")
declare_nav2 = DeclareLaunchArgument("nav2", default_value="False", description="Launch Nav2 stack")
declare_slam = DeclareLaunchArgument("slam", default_value="False", description="Launch SLAM Toolbox")
declare_map = DeclareLaunchArgument(
    "map",
    default_value=os.path.join(
        edubot_share_dir,
        "maps",
        "m215a_saved_map.yaml",  ###! CHANGE ONLY THIS .yaml FOR DEFAULT MAP
    ),
    description="Full path to map YAML file",
)
# Launch configuration variables to be use in nodes and launch files below
use_sim_time = LaunchConfiguration("use_sim_time")
slam = LaunchConfiguration("slam")
map_file = LaunchConfiguration("map")
use_nav2 = LaunchConfiguration("nav2")


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


# SICK TiM561 2D LiDAR node - has inbuilt filtering and significant better performance than LDS01
def sick_tim561_lidar():
    sick_scan_xd_share_dir = get_package_share_directory("sick_scan_xd")
    launch_file_path = os.path.join(sick_scan_xd_share_dir, "launch", "sick_tim_5xx.launch")
    return Node(
        package="sick_scan_xd",
        executable="sick_generic_caller",
        output="screen",
        arguments=[
            launch_file_path,
            "hostname:=192.168.71.71",
            "cloud_topic:=scan_cloud",
            "laserscan_topic:=scan",
            "frame_id:=lidar_link",
            "nodename:=sick_tim561_lidar",
            "tf_publish_rate:=0.0",
            "range_min:=0.1",
        ],
        remappings=[
            ("imu", "/sick_tim561_lidar/imu_placeholder"),  # Placeholder remap to avoid conflicts
        ],
        # Restart policy for robustness
        respawn=True,
        respawn_delay=10.0,
    )


# USB camera node - usb_cam driver (https://github.com/ros-drivers/usb_cam)
def usb_camera(
    param_path: str = "/config/camera_params.yaml",
    camera_name: str = "camera",
):
    """
    Launch a USB camera node with independent parameters and topic namespace.

    Args:
        param_path: Path to camera parameter YAML file (relative to edubot share dir)
        camera_name: Unique node and namespace name for this camera (e.g., "camera_1", "camera_2")
    """
    return Node(
        package="usb_cam",
        executable="usb_cam_node_exe",
        name=camera_name,
        namespace=camera_name,
        parameters=[edubot_share_dir + param_path],
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


def nav2_bringup():
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(edubot_share_dir, "launch", "nav2_bringup_launch.py")]),
        condition=IfCondition(use_nav2),  # Only launch nav2 if launch argument "nav2" is True
        launch_arguments=[
            ("use_sim_time", use_sim_time),
            ("map", map_file),
            ("slam", slam),
        ],
    )


def generate_launch_description():
    """
    Generate the launch description for starting up the EduBot nodes.

    Returns:
        LaunchDescription containing all necessary nodes for the EduBot basic functionality.
    """

    ld = LaunchDescription()
    # Declare launch arguments
    ld.add_action(declare_use_sim_time)
    ld.add_action(declare_slam)
    ld.add_action(declare_map)
    ld.add_action(declare_nav2)

    # Robot communication bridge and description
    ld.add_action(edubot_bridge())
    ld.add_action(edubot_description())

    # Sensor related nodes
    # ld.add_action(lds01_lidar()) #* Old LiDAR model, replaced by SICK TiM561
    # ld.add_action(lds01_lidar_filter()) #* Old LiDAR model, replaced by SICK TiM561
    ld.add_action(sick_tim561_lidar())
    ld.add_action(usb_camera(param_path="/config/camera_1_params.yaml", camera_name="camera_1"))
    ld.add_action(usb_camera(param_path="/config/camera_2_params.yaml", camera_name="camera_2"))
    # ld.add_action(imu_node()) #* Not used currently
    # ld.add_action(imu_filter()) #* Not used currently
    ld.add_action(ekf_odom())

    # Nav2 bringup
    # ld.add_action(nav2_bringup()) #* Not used currently

    return ld
