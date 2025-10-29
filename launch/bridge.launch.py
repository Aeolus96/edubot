"""
bridge.launch.py
Launch file for the edubot ROS 2 bridge components.

This launch file starts both the serial bridge node and the wheel odometry node
with appropriate parameters for the edubot hardware configuration.

The serial bridge handles communication with the PRIZM motor controller, while
the wheel odometry node computes robot pose from wheel joint states.
"""

from launch_ros.actions import Node

from launch import LaunchDescription


# Serial bridge node - handles PRIZM communication
def serial_bridge():
    return Node(
        package="edubot",
        executable="edubot_serial_bridge",
        name="edubot_serial_bridge",
        output="screen",
        parameters=[
            {"serial_port_device": "/dev/edubot_prizm"},
            {"serial_baud_rate": 115200},
            {"left_wheel_joint_name": "left_wheel_joint"},
            {"right_wheel_joint_name": "right_wheel_joint"},
            {"command_transmission_rate_hz": 30.0},
        ],
        # Restart policy for robustness
        respawn=True,
        respawn_delay=2.0,
    )


# Wheel odometry node - computes pose from joint states
def wheel_odometry_node():
    return Node(
        package="edubot",
        executable="edubot_wheel_odom",
        name="edubot_wheel_odom",
        output="screen",
        parameters=[
            {"left_wheel_joint_name": "left_wheel_joint"},
            {"right_wheel_joint_name": "right_wheel_joint"},
            {"wheel_radius_meters": 0.0508},  # 4-inch diameter wheels
            {"wheelbase_track_width_meters": 0.28636},  # Measured wheelbase
            {"odom_frame_id": "odom"},
            {"base_link_frame_id": "base_footprint"},
            {"publish_odom_transform": True},  # Enable TF for RViz, Disable if using external localization
        ],
        # Restart policy for robustness
        respawn=True,
        respawn_delay=2.0,
    )


def generate_launch_description():
    """
    Generate the launch description for the edubot bridge.

    Returns:
        LaunchDescription containing both bridge nodes with configured parameters
    """
    ld = LaunchDescription()
    ld.add_action(serial_bridge())
    ld.add_action(wheel_odometry_node())
    return ld
