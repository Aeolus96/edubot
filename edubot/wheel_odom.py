#!/usr/bin/env python3
"""
wheel_odom.py
ROS 2 node that computes odometry from wheel joint states using differential drive kinematics.

Responsibilities:
- Subscribe to /joint_states and extract wheel joint positions and velocities.
- Integrate wheel motion to compute robot pose (x, y, yaw) in the odom frame.
- Publish nav_msgs/Odometry with pose and twist information.
- Optionally broadcast odom->base_link TF transform for RViz visualization.
- Use REP-105 compliant frame naming (odom parent, base_link child).

The node implements basic dead-reckoning using wheel encoder data. For improved
accuracy with sensor fusion, the output can be consumed by robot_localization
which will fuse wheel odometry with IMU and other sensors.
"""

import math
from typing import Optional

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import JointState
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Quaternion, TransformStamped

from tf2_ros import TransformBroadcaster


class WheelOdometryNode(Node):
    """
    Differential drive wheel odometry computation node.

    This node subscribes to wheel joint states and integrates the motion to
    provide robot pose and velocity estimates. The integration uses simple
    Euler integration which is suitable for the typical speeds and update
    rates of mobile robots.
    """

    def __init__(self):
        super().__init__("edubot_wheel_odometry")

        # Declare parameters with descriptive names and reasonable defaults
        self.declare_parameter("left_wheel_joint_name", "wheel_left_joint")
        self.declare_parameter("right_wheel_joint_name", "wheel_right_joint")
        self.declare_parameter("wheel_radius_meters", 0.0508)  # 4-inch diameter wheels
        self.declare_parameter("wheelbase_track_width_meters", 0.28636)  # Distance between wheel centers
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_link_frame_id", "base_link")
        # IMPORTANT: when using robot_localization, that node should be the sole publisher of odom->base_* TF
        self.declare_parameter("publish_odom_transform", False)  # Set false when robot_localization handles TF

        # Extract parameter values
        self.left_wheel_joint_name = self.get_parameter("left_wheel_joint_name").get_parameter_value().string_value
        self.right_wheel_joint_name = self.get_parameter("right_wheel_joint_name").get_parameter_value().string_value
        self.wheel_radius_meters = float(self.get_parameter("wheel_radius_meters").get_parameter_value().double_value)
        self.wheelbase_track_width_meters = float(
            self.get_parameter("wheelbase_track_width_meters").get_parameter_value().double_value
        )
        self.odom_frame_id = self.get_parameter("odom_frame_id").get_parameter_value().string_value
        self.base_link_frame_id = self.get_parameter("base_link_frame_id").get_parameter_value().string_value
        self.should_publish_transform = bool(
            self.get_parameter("publish_odom_transform").get_parameter_value().bool_value
        )

        # Robot pose state in the odom frame
        self.robot_x_position = 0.0
        self.robot_y_position = 0.0
        self.robot_yaw_angle = 0.0

        # State tracking for integration
        self.previous_timestamp: Optional[float] = None
        self.previous_left_wheel_position = None
        self.previous_right_wheel_position = None

        # ROS interfaces
        # Publish wheel odometry on a dedicated topic to keep roles separate from EKF's TF publisher
        self.odometry_publisher = self.create_publisher(Odometry, "wheel/odometry", 10)
        self.joint_states_subscriber = self.create_subscription(
            JointState, "joint_states", self.handle_joint_state_message, 10
        )

        # TF broadcaster for RViz visualization (optional)
        self.transform_broadcaster = TransformBroadcaster(self) if self.should_publish_transform else None

        self.get_logger().info("Wheel odometry node ready")

    def handle_joint_state_message(self, joint_state_message: JointState):
        """
        Process joint state message and update odometry.

        This function extracts wheel joint positions, computes the robot's motion
        since the last update, integrates the pose, and publishes the result as
        an Odometry message.

        Args:
            joint_state_message: JointState message containing wheel joint data
        """
        # Find wheel joint indices in the message
        try:
            left_wheel_index = joint_state_message.name.index(self.left_wheel_joint_name)
            right_wheel_index = joint_state_message.name.index(self.right_wheel_joint_name)
        except ValueError:
            # Required joints not found in this message, skip
            return

        # Extract wheel positions (radians)
        left_wheel_position_radians = float(joint_state_message.position[left_wheel_index])
        right_wheel_position_radians = float(joint_state_message.position[right_wheel_index])

        # Get current timestamp
        current_time = self.get_clock().now()
        current_timestamp_seconds = (
            float(current_time.seconds_nanoseconds()[0]) + float(current_time.seconds_nanoseconds()[1]) * 1e-9
        )

        # Skip first message to establish baseline
        if self.previous_timestamp is None:
            self.previous_timestamp = current_timestamp_seconds
            self.previous_left_wheel_position = left_wheel_position_radians
            self.previous_right_wheel_position = right_wheel_position_radians
            return

        # Compute time step and wheel motion
        time_delta_seconds = max(1e-6, current_timestamp_seconds - self.previous_timestamp)

        # Compute unwrapped wheel angle differences
        left_wheel_angle_delta = self.compute_unwrapped_angular_difference(
            self.previous_left_wheel_position, left_wheel_position_radians
        )
        right_wheel_angle_delta = self.compute_unwrapped_angular_difference(
            self.previous_right_wheel_position, right_wheel_position_radians
        )

        # Compute wheel angular velocities
        left_wheel_angular_velocity = left_wheel_angle_delta / time_delta_seconds
        right_wheel_angular_velocity = right_wheel_angle_delta / time_delta_seconds

        # Convert to robot body-frame velocities using differential drive kinematics
        # Linear velocity is the average of wheel tangential velocities
        robot_linear_velocity = (
            self.wheel_radius_meters * 0.5 * (left_wheel_angular_velocity + right_wheel_angular_velocity)
        )

        # Angular velocity is the difference of wheel tangential velocities divided by track width
        robot_angular_velocity = (
            self.wheel_radius_meters
            * (right_wheel_angular_velocity - left_wheel_angular_velocity)
            / self.wheelbase_track_width_meters
        )

        # Integrate robot pose using simple Euler integration
        # This assumes small time steps and moderate angular velocities
        self.robot_x_position += robot_linear_velocity * math.cos(self.robot_yaw_angle) * time_delta_seconds
        self.robot_y_position += robot_linear_velocity * math.sin(self.robot_yaw_angle) * time_delta_seconds
        self.robot_yaw_angle = self.wrap_angle_to_pi_range(
            self.robot_yaw_angle + robot_angular_velocity * time_delta_seconds
        )

        # Create and publish Odometry message
        odometry_message = Odometry()
        odometry_message.header.stamp = current_time.to_msg()
        odometry_message.header.frame_id = self.odom_frame_id
        odometry_message.child_frame_id = self.base_link_frame_id

        # Set pose
        odometry_message.pose.pose.position.x = self.robot_x_position
        odometry_message.pose.pose.position.y = self.robot_y_position
        odometry_message.pose.pose.position.z = 0.0
        odometry_message.pose.pose.orientation = self.yaw_angle_to_quaternion(self.robot_yaw_angle)

        # Set twist (velocities in the base_link frame)
        odometry_message.twist.twist.linear.x = robot_linear_velocity
        odometry_message.twist.twist.linear.y = 0.0  # No lateral motion for differential drive
        odometry_message.twist.twist.linear.z = 0.0
        odometry_message.twist.twist.angular.x = 0.0
        odometry_message.twist.twist.angular.y = 0.0
        odometry_message.twist.twist.angular.z = robot_angular_velocity

        # Covariances:
        # - Keep reasonable values on the fields EKF uses (vx, vyaw).
        # - Use large-but-finite values on unused axes to avoid numerical extremes.

        # fmt: off
        odometry_message.pose.covariance = [
            0.05,  0.0,   0.0,   0.0,   0.0,   0.0,   # x
            0.0,   0.05,  0.0,   0.0,   0.0,   0.0,   # y
            0.0,   0.0,   100.0, 0.0,   0.0,   0.0,   # z (unused)
            0.0,   0.0,   0.0,   100.0 ,0.0,   0.0,   # roll (unused)
            0.0,   0.0,   0.0,   0.0,   100.0, 0.0,   # pitch (unused)
            0.0,   0.0,   0.0,   0.0,   0.0,   0.2,   # yaw
        ]

        odometry_message.twist.covariance = [
            0.02,  0.0,    0.0,    0.0,    0.0,    0.0,   # vx
            0.0,   100.0,  0.0,    0.0,    0.0,    0.0,   # vy (unused)
            0.0,   0.0,    100.0,  0.0,    0.0,    0.0,   # vz (unused)
            0.0,   0.0,    0.0,    100.0,  0.0,    0.0,   # wx (unused)
            0.0,   0.0,    0.0,    0.0,    100.0,  0.0,   # wy (unused)
            0.0,   0.0,    0.0,    0.0,    0.0,   0.05,   # wz (vyaw)
        ]
        # fmt: on

        self.odometry_publisher.publish(odometry_message)

        # Broadcast TF transform only if explicitly enabled (should be false when using EKF)
        if self.should_publish_transform and self.transform_broadcaster:
            transform_message = TransformStamped()
            transform_message.header.stamp = odometry_message.header.stamp
            transform_message.header.frame_id = self.odom_frame_id
            transform_message.child_frame_id = self.base_link_frame_id

            transform_message.transform.translation.x = self.robot_x_position
            transform_message.transform.translation.y = self.robot_y_position
            transform_message.transform.translation.z = 0.0
            transform_message.transform.rotation = odometry_message.pose.pose.orientation

            self.transform_broadcaster.sendTransform(transform_message)

        # Update state for next iteration
        self.previous_timestamp = current_timestamp_seconds
        self.previous_left_wheel_position = left_wheel_position_radians
        self.previous_right_wheel_position = right_wheel_position_radians

    @staticmethod
    def compute_unwrapped_angular_difference(previous_angle_radians: float, current_angle_radians: float) -> float:
        """
        Compute shortest angular difference handling wraparound at 0/2π boundary.

        Args:
            previous_angle_radians: Previous angle in [0, 2π)
            current_angle_radians: Current angle in [0, 2π)

        Returns:
            Shortest signed angular difference
        """
        two_pi = 2.0 * math.pi
        angle_difference = current_angle_radians - previous_angle_radians

        if angle_difference > math.pi:
            angle_difference -= two_pi
        elif angle_difference < -math.pi:
            angle_difference += two_pi

        return angle_difference

    @staticmethod
    def wrap_angle_to_pi_range(angle_radians: float) -> float:
        """
        Wrap angle to [-π, π] range.

        Args:
            angle_radians: Input angle in radians

        Returns:
            Wrapped angle in [-π, π]
        """
        while angle_radians > math.pi:
            angle_radians -= 2.0 * math.pi
        while angle_radians < -math.pi:
            angle_radians += 2.0 * math.pi
        return angle_radians

    @staticmethod
    def yaw_angle_to_quaternion(yaw_radians: float) -> Quaternion:
        """
        Convert yaw angle to quaternion representation.

        Args:
            yaw_radians: Yaw angle in radians

        Returns:
            Quaternion representing rotation about z-axis
        """
        quaternion = Quaternion()
        quaternion.w = math.cos(0.5 * yaw_radians)
        quaternion.x = 0.0
        quaternion.y = 0.0
        quaternion.z = math.sin(0.5 * yaw_radians)
        return quaternion


def main():
    """
    Main entry point for the wheel odometry node.
    """
    rclpy.init()

    node = WheelOdometryNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
