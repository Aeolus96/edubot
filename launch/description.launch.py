import os

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

from launch import LaunchDescription


# Find the package directory as installed by setup.py
pkg_dir = get_package_share_directory("edubot")

# Find the EduBot's URDF (Universal Robot Description Format) file path
urdf_file = os.path.join(pkg_dir, "urdf", "edubot.urdf")

# Read the URDF file to get the robot description (XML format)
with open(urdf_file, "r") as f:
    robot_description = f.read()


# Define the robot_state_publisher node. Publishes the state of the robot to tf
def robot_state_publisher_node():
    return Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[
            {"use_sim_time": False},
            {"robot_description": robot_description},
        ],
    )


# Define the joint_state_publisher node. Publishes the joint states of the robot
def joint_state_publisher_node():
    return Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        name="joint_state_publisher",
        output="screen",
        parameters=[
            {"use_sim_time": False},
            {"robot_description": robot_description},
        ],
    )


# Generate the launch description with the defined nodes. This is what actually launches
# the nodes when the launch file is ran from the command line.
def generate_launch_description():
    ld = LaunchDescription()
    ld.add_action(robot_state_publisher_node())
    ld.add_action(joint_state_publisher_node())
    return ld
