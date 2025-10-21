#!/usr/bin/env python3
"""
serial_bridge.py
ROS 2 node that directly bridges /cmd_vel to the PRIZM over PacketSerial (COBS) and publishes telemetry.

Simplified behavior:
- On every /cmd_vel message, immediately build and send a velocity command frame (no latching, no timers).
- In a background worker, continuously read complete COBS frames using read_until(b'\x00'), CRC-check, and publish:
  * /joint_states (wheel_left_joint, wheel_right_joint) with wrapped positions [0, 2π) and computed velocities.
  * /battery_state with voltage and standard flags.
Resilience:
- If open fails or the USB cable is unplugged, print a clear message and retry open every few seconds.
- After open, flush input/output buffers and start fresh.
- If connected but no telemetry arrives for several seconds, print a throttled warning to aid debugging.
"""

import math
import struct
import threading
import time
from typing import Optional

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import JointState, BatteryState
from geometry_msgs.msg import Twist

import serial
from cobs import cobs

PKT_CMD_VELOCITY = 0x10
PKT_TEL_WHEELS = 0x21
PKT_TEL_STATUS = 0x22


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC16-CCITT (poly 0x1021, init 0xFFFF), must match firmware implementation."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def build_cmd(linear_x_mps: float, angular_z_rps: float, enable: bool) -> bytes:
    """Build a COBS-framed velocity command: [0x10][i16 mm/s][i16 mrad/s][u8 enable][u16 crc] + delimiter."""
    lin_mmps = int(round(linear_x_mps * 1000.0))
    ang_mrps = int(round(angular_z_rps * 1000.0))
    payload_wo_crc = struct.pack("<BhhB", PKT_CMD_VELOCITY, lin_mmps, ang_mrps, 1 if enable else 0)
    payload = payload_wo_crc + struct.pack("<H", crc16_ccitt(payload_wo_crc))
    return cobs.encode(payload) + b"\x00"


class SerialBridge(Node):
    """
    Minimal, robust ROS 2 bridge:
    - Default QoS for publishers/subscribers.
    - Immediate send on /cmd_vel.
    - read_until-based COBS frame parsing with CRC, plus auto-reconnect and health logs.
    """

    def __init__(self):
        super().__init__("edubot_serial_bridge")
        # Parameters
        self.declare_parameter("serial_port_device", "/dev/edubot_prizm")
        self.declare_parameter("serial_baud_rate", 115200)
        self.declare_parameter("left_wheel_joint_name", "wheel_left_joint")
        self.declare_parameter("right_wheel_joint_name", "wheel_right_joint")
        self.declare_parameter("reconnect_interval_seconds", 2.0)
        self.declare_parameter("no_telemetry_warn_seconds", 3.0)

        self.port = self.get_parameter("serial_port_device").get_parameter_value().string_value
        self.baud = self.get_parameter("serial_baud_rate").get_parameter_value().integer_value
        self.left_joint = self.get_parameter("left_wheel_joint_name").get_parameter_value().string_value
        self.right_joint = self.get_parameter("right_wheel_joint_name").get_parameter_value().string_value
        self.reconnect_s = self.get_parameter("reconnect_interval_seconds").get_parameter_value().double_value
        self.no_tel_s = self.get_parameter("no_telemetry_warn_seconds").get_parameter_value().double_value

        # ROS interfaces (default QoS)
        self.joint_pub = self.create_publisher(JointState, "joint_states", 10)
        self.batt_pub = self.create_publisher(BatteryState, "battery_state", 10)
        self.create_subscription(Twist, "cmd_vel", self.on_cmd_vel, 10)

        # Serial and state
        self.ser_lock = threading.Lock()
        self.ser: Optional[serial.Serial] = None
        self.stop_evt = threading.Event()

        self.last_tel_t = time.monotonic()
        self.last_tel_warn = 0.0
        self.prev_left = None
        self.prev_right = None
        self.prev_t = None

        # Start worker
        threading.Thread(target=self.worker, name="SerialWorker", daemon=True).start()
        self.get_logger().info(f"Serial bridge ready on {self.port}@{self.baud}")

    def on_cmd_vel(self, msg: Twist):
        """Immediately send one command frame for each Twist received."""
        lin = float(msg.linear.x)
        ang = float(msg.angular.z)
        enable = (abs(lin) > 1e-3) or (abs(ang) > 1e-3)
        frame = build_cmd(lin, ang, enable)
        with self.ser_lock:
            if not self.ser:
                self.get_logger().warn("Serial not connected: dropping cmd_vel")
                return
            try:
                self.ser.write(frame)
            except Exception as e:
                self.get_logger().warn(f"Serial write failed: {e}")
                self._close_locked()

    def worker(self):
        """Open serial (retry), then read frames with read_until(b'\\x00'), decode, CRC-check, and publish."""
        while not self.stop_evt.is_set():
            if not self._ensure_open():
                time.sleep(self.reconnect_s)
                continue
            try:
                # Read one frame delimited by 0x00 (COBS guarantee: payload contains no 0x00)
                with self.ser_lock:
                    if not self.ser:
                        continue
                    raw = self.ser.read_until(b"\x00")
                if not raw:
                    # Connection idle; check telemetry health
                    now = time.monotonic()
                    if (now - self.last_tel_t) > self.no_tel_s and (now - self.last_tel_warn) > self.no_tel_s:
                        self.get_logger().warn("Serial connected but no telemetry received recently")
                        self.last_tel_warn = now
                    time.sleep(0.01)
                    continue
                # Drop the trailing delimiter if present
                if raw.endswith(b"\x00"):
                    raw = raw[:-1]
                if not raw:
                    continue
                # COBS decode and CRC-check
                try:
                    payload = cobs.decode(raw)
                except Exception:
                    # Decoder failed (likely mid-stream noise or stale data); continue
                    continue
                if len(payload) < 3:
                    continue
                pkt = payload[0]
                crc_rx = struct.unpack_from("<H", payload, len(payload) - 2)[0]
                if crc_rx != crc16_ccitt(payload[:-2]):
                    continue
                self.last_tel_t = time.monotonic()
                if pkt == PKT_TEL_WHEELS and len(payload) == 7:
                    self.handle_wheels(payload)
                elif pkt == PKT_TEL_STATUS and len(payload) == 9:
                    self.handle_status(payload)
                # Ignore other types silently
            except Exception as e:
                self.get_logger().warn(f"Serial read error: {e}")
                with self.ser_lock:
                    self._close_locked()
                time.sleep(self.reconnect_s)

    def handle_wheels(self, payload: bytes):
        """Publish JointState with wrapped positions and computed velocities."""
        left_deg, right_deg = struct.unpack_from("<HH", payload, 1)
        left_rad = math.radians(left_deg % 360)
        right_rad = math.radians(right_deg % 360)
        now_msg = self.get_clock().now()
        sec, nsec = now_msg.seconds_nanoseconds()
        t = float(sec) + 1e-9 * float(nsec)

        vL = 0.0
        vR = 0.0
        if self.prev_left is not None and self.prev_right is not None and self.prev_t is not None:
            dt = max(1e-6, t - self.prev_t)
            dL = self.unwrap(self.prev_left, left_rad)
            dR = self.unwrap(self.prev_right, right_rad)
            vL = dL / dt
            vR = dR / dt

        self.prev_left = left_rad
        self.prev_right = right_rad
        self.prev_t = t

        js = JointState()
        js.header.stamp = now_msg.to_msg()
        js.name = [self.left_joint, self.right_joint]
        js.position = [left_rad, right_rad]
        js.velocity = [vL, vR]
        self.joint_pub.publish(js)

    def handle_status(self, payload: bytes):
        """Publish BatteryState with voltage and standard flags; uptime is diagnostic only."""
        batt_cV, uptime_ms = struct.unpack_from("<HI", payload, 1)
        msg = BatteryState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.voltage = float(batt_cV) / 100.0
        msg.current = float("nan")
        msg.charge = float("nan")
        msg.capacity = float("nan")
        msg.design_capacity = float("nan")
        msg.percentage = float("nan")
        msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_UNKNOWN
        msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_UNKNOWN
        msg.present = True
        self.batt_pub.publish(msg)

    @staticmethod
    def unwrap(prev_wrapped: float, curr_wrapped: float) -> float:
        """Shortest signed delta for values in [0, 2π)."""
        two_pi = 2.0 * math.pi
        d = curr_wrapped - prev_wrapped
        if d > math.pi:
            d -= two_pi
        elif d < -math.pi:
            d += two_pi
        return d

    def _ensure_open(self) -> bool:
        """Open serial if needed; flush buffers after open; disable DTR/RTS; return True if connected."""
        with self.ser_lock:
            if self.ser:
                return True
            try:
                self.ser = serial.Serial(
                    self.port,
                    self.baud,
                    timeout=0.05,  # allows read_until to time out quickly
                    write_timeout=0.2,
                    dsrdtr=False,
                    rtscts=False,
                )
                # Prevent autoreset and clear any stale bytes
                try:
                    self.ser.setDTR(False)
                    self.ser.setRTS(False)
                except Exception:
                    pass
                try:
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                except Exception:
                    pass
                self.last_tel_t = time.monotonic()
                self.last_tel_warn = 0.0
                self.get_logger().info(f"Connected to {self.port}@{self.baud}")
                return True
            except Exception as e:
                self.ser = None
                self.get_logger().warn(f"Open failed for {self.port}: {e}")
                return False

    def _close_locked(self):
        """Close serial (caller holds ser_lock)."""
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        finally:
            self.ser = None

    def destroy_node(self):
        """Stop worker and close serial cleanly."""
        self.stop_evt.set()
        time.sleep(0.05)
        with self.ser_lock:
            self._close_locked()
        super().destroy_node()


def main():
    rclpy.init()
    node = SerialBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
