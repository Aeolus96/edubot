#!/usr/bin/env python3

"""
edubot_udev_setup_interactive.py

Interactive udev rule helper (Ubuntu 24.04, ROS 2 Jazzy).
- Creates stable symlinks as direct /dev entries: /dev/edubot_<name> and (for cameras) /dev/edubot_<name>_meta.
- Splits UVC capture vs metadata nodes using ENV{ID_V4L_CAPABILITIES} and ATTR{index}.
"""

import glob
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

RULES_FILE = "/etc/udev/rules.d/99-edubot.rules"

# -------------------------------
# Shell helpers
# -------------------------------


def run_command(args: List[str]) -> str:
    """Run a command and return stdout text."""
    proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.stdout


def try_run_command(args: List[str]) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def require_root_via_sudo():
    """If not root, re-exec this script using sudo -E to request elevation."""
    if os.geteuid() == 0:
        return
    script_path = os.path.abspath(sys.argv[0])
    print("\nThis tool needs administrator privileges to write udev rules; a sudo prompt will appear.\n")
    os.execlp("sudo", "sudo", "-E", sys.executable, script_path)


# -------------------------------
# udev attribute discovery
# -------------------------------


def discover_usb_parent_block(attribute_walk_text: str) -> Optional[str]:
    """From `udevadm info --attribute-walk --name`, find the first parent block with SUBSYSTEMS==\"usb\"."""
    blocks = re.split(r"\n(?=looking at )", attribute_walk_text, flags=re.IGNORECASE)
    for blk in blocks:
        if re.search(r'SUBSYSTEMS==\s*"usb"', blk, flags=re.IGNORECASE):
            return blk
    return None


def extract_attr(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1) if m else None


def get_device_usb_identifiers(devnode: str) -> Dict[str, Optional[str]]:
    """Extract USB identifiers (idVendor, idProduct, serial if present) for a device node."""
    walk = run_command(["udevadm", "info", "--attribute-walk", "--name", devnode])
    usb_blk = discover_usb_parent_block(walk) or ""

    id_vendor = extract_attr(r'ATTRS\{\s*idVendor\s*\}==\s*"([0-9a-fA-F]{4})"', usb_blk)
    id_product = extract_attr(r'ATTRS\{\s*idProduct\s*\}==\s*"([0-9a-fA-F]{4})"', usb_blk)
    serial = extract_attr(r'ATTRS\{\s*serial\s*\}==\s*"([^"]+)"', usb_blk)

    props = run_command(["udevadm", "info", "--query=property", "--name", devnode])
    if not id_vendor:
        id_vendor = extract_attr(r"^ID_VENDOR_ID=(\w+)$", props)
    if not id_product:
        id_product = extract_attr(r"^ID_MODEL_ID=(\w+)$", props)
    if not serial:
        serial = extract_attr(r"^ID_SERIAL_SHORT=(.+)$", props)

    return {
        "idVendor": id_vendor.lower() if id_vendor else None,
        "idProduct": id_product.lower() if id_product else None,
        "serial": serial,
    }


def get_v4l2_index(devnode: str) -> Optional[int]:
    """Read /sys/class/video4linux/<node>/index to determine the node index."""
    base = os.path.basename(devnode)
    sys_index = f"/sys/class/video4linux/{base}/index"
    try:
        with open(sys_index, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def get_v4l2_caps(devnode: str) -> str:
    """Return the ID_V4L_CAPABILITIES string for a node, or empty if unavailable."""
    code, out, _ = try_run_command(["udevadm", "info", "--query=property", "--name", devnode])
    if code != 0:
        return ""
    m = re.search(r"^ID_V4L_CAPABILITIES=(.*)$", out, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


# -------------------------------
# Rule generation
# -------------------------------


def _sanitize_symlink_basename(name: str) -> str:
    """Lower-case, replace non [a-z0-9_] with '_', collapse underscores."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "device"


def make_dev_symlink(name: str) -> str:
    """Return udev SYMLINK target (relative to /dev) as edubot_<name>."""
    return f"edubot_{_sanitize_symlink_basename(name)}"


def build_serial_rule(id_vendor: str, id_product: str, serial: Optional[str], link_target: str, perms: str) -> str:
    """Build udev rule for serial devices (/dev/ttyUSB*, /dev/ttyACM*)."""
    parts = [
        'ACTION=="add"',
        'SUBSYSTEM=="tty"',
        f'ATTRS{{idVendor}}=="{id_vendor}"',
        f'ATTRS{{idProduct}}=="{id_product}"',
    ]
    if serial:
        parts.append(f'ATTRS{{serial}}=="{serial}"')

    assigns = [f'SYMLINK+="{link_target}"']
    if perms == "safe":
        assigns += ['MODE="0660"', 'GROUP="dialout"', 'TAG+="uaccess"']
    else:
        assigns += ['MODE="0666"']

    return ", ".join(parts + assigns)


def build_camera_rules_split(
    id_vendor: str,
    id_product: str,
    serial: Optional[str],
    link_base: str,
    perms: str,
    capture_index: int,
    metadata_index: int,
) -> List[str]:
    """
    Build two rules for V4L2 cameras:
    - capture: ENV{ID_V4L_CAPABILITIES} contains 'capture' and ATTR{index}==capture_index -> SYMLINK+=link_base
    - metadata: ATTR{index}==metadata_index -> SYMLINK+=link_base + '_meta'
    """
    common = [
        'ACTION=="add"',
        'SUBSYSTEM=="video4linux"',
        'KERNEL=="video[0-9]*"',
        f'ATTRS{{idVendor}}=="{id_vendor}"',
        f'ATTRS{{idProduct}}=="{id_product}"',
    ]
    if serial:
        common.append(f'ATTRS{{serial}}=="{serial}"')

    def assigns(name: str) -> List[str]:
        a = [f'SYMLINK+="{name}"']
        if perms == "safe":
            a += ['MODE="0660"', 'GROUP="video"', 'TAG+="uaccess"']
        else:
            a += ['MODE="0666"']
        return a

    # Capture rule
    capture_rule = ", ".join(
        common
        + [
            f'ATTR{{index}}=="{capture_index}"',
            'ENV{ID_V4L_CAPABILITIES}=="*capture*"',
        ]
        + assigns(link_base)
    )

    # Metadata rule
    metadata_rule = ", ".join(
        common
        + [
            f'ATTR{{index}}=="{metadata_index}"',
        ]
        + assigns(link_base + "_meta")
    )

    return [capture_rule, metadata_rule]


def append_rule(rule_line: str) -> None:
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "a", encoding="utf-8") as f:
        f.write(rule_line + "\n")
    print(f"[ok] Appended rule to {RULES_FILE}")


# -------------------------------
# Device discovery UX
# -------------------------------


def list_candidates() -> List[str]:
    """Return sorted list of likely device nodes to choose from."""
    paths = set()
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/video*"):
        for p in glob.glob(pattern):
            if os.path.exists(p):
                paths.add(p)
    return sorted(paths)


def snapshot_candidate_set() -> set:
    """Snapshot set of candidate device nodes for diffing."""
    return set(list_candidates())


def diff_new_nodes(before: set, after: set) -> List[str]:
    return sorted(list(after - before))


def choose_perms_style() -> str:
    print("\nPermissions style:")
    print(" 1) Safe (MODE=0660 + TAG+=uaccess; RECOMMENDED)")
    print(" 2) World-writable (MODE=0666; workaround but less secure)")
    while True:
        choice = input("Select 1/2: ").strip()
        if choice == "1":
            return "safe"
        if choice == "2":
            return "world"
        print("Please enter 1 or 2.")


def identify_device_interactively() -> Optional[str]:
    print("\nDevice identification:")
    print(" 1) List of current serial/camera nodes and pick one")
    print(" 2) Guided plug-in (RECOMMENDED)")
    print(" 3) Type the full path manually (/dev/ttyUSB0 or /dev/video0)")
    while True:
        choice = input("Select 1/2/3: ").strip()
        if choice == "1":
            candidates = list_candidates()
            if not candidates:
                print("No candidate devices found.")
                return None
            for idx, p in enumerate(candidates, 1):
                print(f" {idx}) {p}")
            while True:
                sel = input(f"Pick 1-{len(candidates)}: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(candidates):
                    return candidates[int(sel) - 1]
                print("Invalid selection.")
        elif choice == "2":
            input("Unplug devices now, then press Enter...")
            base = snapshot_candidate_set()
            input("Plug in ONE device, wait 2-3 seconds, then press Enter...")
            time.sleep(2.0)
            after = snapshot_candidate_set()
            new_nodes = diff_new_nodes(base, after)
            if not new_nodes:
                print("No new device nodes detected.")
                return None
            print("Detected new device nodes:")
            for idx, p in enumerate(new_nodes, 1):
                print(f" {idx}) {p}")
            while True:
                sel = input(f"Pick 1-{len(new_nodes)}: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(new_nodes):
                    return new_nodes[int(sel) - 1]
                print("Invalid selection.")
        elif choice == "3":
            p = input("Enter device path: ").strip()
            if os.path.exists(p):
                return p
            print("That path does not exist.")
        else:
            print("Please enter 1, 2, or 3.")


def classify_device(devnode: str) -> str:
    """Return 'serial' or 'camera' based on path."""
    base = os.path.basename(devnode)
    if base.startswith(("ttyUSB", "ttyACM")) or "/tty" in devnode:
        return "serial"
    return "camera" if base.startswith("video") else "camera"


# -------------------------------
# Main workflow
# -------------------------------


def add_one_device():
    devnode = identify_device_interactively()
    if not devnode:
        print("Skipping; could not identify a device.")
        return

    dev_type = classify_device(devnode)
    print(f"\nSelected device: {devnode} [{dev_type}]")

    link_name = ""
    while not link_name:
        link_name = input("Enter base symlink name (e.g., camera, imu, lidar): ").strip()
    link_base = make_dev_symlink(link_name)

    perms = choose_perms_style()

    print("\nReading USB identifiers (idVendor, idProduct, serial if present)...")
    ids = get_device_usb_identifiers(devnode)
    if not ids.get("idVendor") or not ids.get("idProduct"):
        print("Could not determine idVendor/idProduct; is this a USB-backed device?")
        return

    if dev_type == "serial":
        rule_line = build_serial_rule(ids["idVendor"], ids["idProduct"], ids.get("serial"), link_base, perms)
        print("\n[preview] udev rule:")
        print(rule_line)
        append_rule(rule_line)
        return

    # Camera: emit two rules (capture and metadata)
    idx = get_v4l2_index(devnode)
    caps = get_v4l2_caps(devnode)
    # Default assumption: index 0 is capture, index 1 is metadata
    capture_index = 0
    metadata_index = 1
    # If user selected index 1 first, flip defaults
    if idx == 1 and "capture" not in caps:
        capture_index, metadata_index = 0, 1
    elif idx == 0 and "capture" in caps:
        capture_index, metadata_index = 0, 1
    # Build and append both rules
    rules = build_camera_rules_split(
        ids["idVendor"], ids["idProduct"], ids.get("serial"), link_base, perms, capture_index, metadata_index
    )
    print("\n[preview] udev rules (capture + metadata):")
    for r in rules:
        print(r)
        append_rule(r)


def build_camera_rules_by_devpath(link_base: str, devpath_pattern: str, perms: str) -> List[str]:
    """
    Build two rules for V4L2 cameras using DEVPATH matching (for identical cameras on USB hub).
    - capture: DEVPATH matches pattern and index==0 -> SYMLINK+=link_base
    - metadata: DEVPATH matches pattern and index==1 -> SYMLINK+=link_base + '_meta'
    """
    common = [
        'ACTION=="add"',
        'SUBSYSTEM=="video4linux"',
        'KERNEL=="video[0-9]*"',
        f'DEVPATH=="{devpath_pattern}"',
    ]

    def assigns(name: str) -> List[str]:
        a = [f'SYMLINK+="{name}"']
        if perms == "safe":
            a += ['MODE="0660"', 'GROUP="video"', 'TAG+="uaccess"']
        else:
            a += ['MODE="0666"']
        return a

    # Capture rule (index 0)
    capture_rule = ", ".join(common + ['ATTR{index}=="0"'] + assigns(link_base))

    # Metadata rule (index 1)
    metadata_rule = ", ".join(common + ['ATTR{index}=="1"'] + assigns(link_base + "_meta"))

    return [capture_rule, metadata_rule]


def add_multiple_cameras():
    """Auto-discover video devices and set up multiple cameras with DEVPATH-based rules."""
    print("\n=== Multi-Camera Setup (DEVPATH-based) ===")
    print("This will auto-detect all cameras and create persistent symlinks.")
    print("Even if cameras swap device nodes, each symlink stays with its physical port.\n")

    # Discover all video devices
    video_devices = sorted(glob.glob("/dev/video[0-9]*"))
    if not video_devices:
        print("No video devices found.")
        return

    # Group by physical device (same DEVPATH base = same camera)
    device_map: Dict[str, List[str]] = {}
    for dev in video_devices:
        try:
            devpath = run_command(["udevadm", "info", "--query=path", "--name", dev]).strip()
            # Extract the USB device path (everything up to the last /video4linux/)
            usb_path = re.sub(r"/video4linux/.*$", "", devpath)
            if usb_path not in device_map:
                device_map[usb_path] = []
            device_map[usb_path].append(dev)
        except Exception:
            pass

    if not device_map:
        print("Could not determine device paths.")
        return

    cameras = list(device_map.items())
    print(f"Found {len(cameras)} camera(s):\n")

    for idx, (usb_path, devs) in enumerate(cameras, 1):
        print(f"{idx}) {', '.join(devs)}")
        print(f"   Path: {usb_path}\n")

    # Ask which ones to configure
    selections = []
    while True:
        try:
            print(f"\nEnter camera number(s) to configure:")
            print(f"  • Single camera:   1")
            print(f"  • Multiple cameras: 1 2")
            print(f"  • Range:           1 2 3")
            print(f"(Valid range: 1-{len(cameras)})\n")
            sel = input("Enter camera numbers: ").strip()
            if not sel:
                print("Please select at least one camera.")
                continue
            selections = [int(x) for x in sel.split()]
            if all(1 <= s <= len(cameras) for s in selections):
                break
            print(f"Invalid: please enter numbers between 1 and {len(cameras)}.")
        except ValueError:
            print("Invalid input: please enter space-separated numbers (e.g., 1 2).")

    # Get permissions style once for all
    perms = choose_perms_style()

    # Configure each selected camera
    for cam_num in selections:
        usb_path, devs = cameras[cam_num - 1]
        devpath = run_command(["udevadm", "info", "--query=path", "--name", devs[0]]).strip()

        # Extract port pattern - handles both direct USB and hub connections
        # Direct USB: /1-4/1-4:1.0 → pattern */1-4/*
        # Hub port: /1-11.2/1-11.2:1.0 → pattern */1-*/1-*.2/*
        hub_match = re.search(r"(1-\d+\.\d+)", devpath)
        direct_match = re.search(r"/(1-\d+)(?:/|:)", devpath)
        
        if hub_match:
            # Hub sub-port connection
            subport_pattern = hub_match.group(1)
            port_num = subport_pattern.split(".")[-1]
            wildcard_pattern = f"*/1-*/1-*.{port_num}/*"
            print(f"Detected hub sub-port: {subport_pattern}")
        elif direct_match:
            # Direct USB connection
            usb_port = direct_match.group(1)
            wildcard_pattern = f"*/{usb_port}/*"
            print(f"Detected direct USB port: {usb_port}")
        else:
            print(f"Could not parse USB port from {devpath}; skipping.")
            continue

        # Ask for symlink name
        link_name = ""
        while not link_name:
            link_name = input(f"Enter symlink name for {', '.join(devs)} (e.g., camera_1): ").strip()
        link_base = make_dev_symlink(link_name)

        # Generate and append rules
        rules = build_camera_rules_by_devpath(link_base, wildcard_pattern, perms)
        print(f"\n[Rules for {link_name}]:")
        for r in rules:
            print(r)
            append_rule(r)

    print("\n[✓] All camera rules added.")


def clear_rules_file():
    """Clear the entire udev rules file."""
    if not os.path.exists(RULES_FILE):
        print(f"Rules file {RULES_FILE} does not exist.")
        return

    print(f"\n⚠️  WARNING: This will DELETE all rules in {RULES_FILE}")
    confirm = input("Are you sure you want to clear all rules? (yes/no): ").strip().lower()
    if confirm == "yes":
        try:
            os.remove(RULES_FILE)
            print(f"[✓] Rules file cleared: {RULES_FILE}")
            print("\nApply changes:")
            print("  sudo udevadm control --reload")
            print("  sudo udevadm trigger")
        except Exception as e:
            print(f"Error: could not remove file: {e}")
    else:
        print("Cancelled.")


def main():
    require_root_via_sudo()

    print("Edubot udev setup — create /dev symlinks for serial devices and USB cameras.\n")
    print("Cameras get two symlinks by default: edubot_<name> (capture) and edubot_<name>_meta (metadata).\n")

    print("Setup mode:")
    print(" 1) Add devices one-by-one (classic mode)")
    print(" 2) Add multiple cameras at once (auto-detect, DEVPATH-based)")
    print(" 3) Clear all udev rules (reset)")
    mode = input("Select 1/2/3 (default 1): ").strip() or "1"

    if mode == "2":
        add_multiple_cameras()
    elif mode == "3":
        clear_rules_file()
    else:
        while True:
            add_one_device()
            again = input("\nAdd another device? (y/n): ").strip().lower()
            if again not in ("y", "yes"):
                break

    print("\n=== Copy-paste these to apply rules now ===")
    print("sudo udevadm control --reload")
    print("sudo udevadm trigger")
    print("==========================================\n")
    print(f"Rules file: {RULES_FILE}")
    print("If a symlink doesn’t appear immediately, try replugging the device.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
