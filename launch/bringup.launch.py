"""Launch file for bringing up the EduBot nodes:
- bridge.launch.py: Launches the serial bridge and wheel odometry.
- description.launch.py: Launches the robot_state_publisher and joint_state_publisher.

"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


# Path to package share directory
edubot_share_dir = get_package_share_directory("edubot")


# Serial bridge and wheel odometry node - handles PRIZM communication
def edubot_bridge():
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(edubot_share_dir, "launch", "bridge.launch.py")])
    )


# Robot description nodes - robot_state_publisher and joint_state_publisher
def edubot_description():
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(edubot_share_dir, "launch", "description.launch.py")])
    )


# 2D LiDAR node - LDS01 driver
def lds01_lidar():
    # Find the package directory for the LDS01 driver
    lds01_share_dir = get_package_share_directory("hls_lfcd_lds_driver")
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(lds01_share_dir, "launch", "hlds_laser.launch.py")]),
        launch_arguments={"port": "/dev/edubot_lidar"}.items(),
    )


# USB camera node - usb_cam driver (https://github.com/ros-drivers/usb_cam)
def usb_camera():
    return Node(
        package="usb_cam",
        executable="usb_cam_node_exe",
        name="usb_cam_node",
        parameters=[edubot_share_dir + "/config/camera_params.yaml"],  # ONLY CHANGE THIS .yaml FOR CAMERA PARAMETERS
        output="screen",
    )


# IMU node - BMI088 driver
def imu_node():
    imu_driver_share_dir = get_package_share_directory("imu_serial_to_ros_publisher")
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(imu_driver_share_dir, "launch", "imu_publisher.launch.py")]),
        launch_arguments={
            "serial_port": "/dev/edubot_imu",
            "frame_id": "imu_link",
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
    ld.add_action(usb_camera())
    ld.add_action(imu_node())
    return ld
